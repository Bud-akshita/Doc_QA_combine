import os
import torch
import numpy as np
import time
import transformers
from transformers import AutoModel
from transformers import AutoTokenizer
import fitz  # PyMuPDF
import io
from PIL import Image
import pytesseract
from langchain_community.vectorstores import FAISS
from langchain.docstore.document import Document
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
import faiss
import pickle
from google.cloud import storage
import tempfile
import shutil
from huggingface_hub import login
import logging
from google.api_core import exceptions as gcs_exceptions

login(token=os.environ.get("HF_TOKEN"))

# Initialize models
tokenizer = AutoTokenizer.from_pretrained('jinaai/jina-embeddings-v2-base-en', trust_remote_code=True)
model = AutoModel.from_pretrained('jinaai/jina-embeddings-v2-base-en', trust_remote_code=True)

# Initialize LLM
groq_api_key = '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'
llm = ChatGroq(groq_api_key=groq_api_key, model_name="llama-3.1-8b-instant")

# Prompt template
prompt = ChatPromptTemplate.from_template(
    """
    Answer the questions based on the provided context only.
    Please provide the most accurate response based on the context and question.
    If the answer cannot be found in the context, respond with "I don't have enough information to answer that question."
    <context>
    {context}
    </context>
    Question: {input}
    """
)

def upload_vectorstore_to_gcs(local_path: str, bucket_name: str, dest_prefix: str):
    """
    Uploads all files from a local vector store folder to GCS under dest_prefix.
    """
    try :
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        
        for root, _, files in os.walk(local_path):
            for file in files:
                local_file_path = os.path.join(root, file)
                # Compute blob name relative to dest_prefix
                rel_path = os.path.relpath(local_file_path, local_path)
                blob_name = os.path.join(dest_prefix, rel_path)
                blob = bucket.blob(blob_name)
                blob.upload_from_filename(local_file_path)
        print(f"Vector store uploaded to gs://{bucket_name}/{dest_prefix}/")
    except gcs_exceptions.NotFound as e:
        logging.error(f"GCS resource not found: {e}")
        raise RuntimeError(f"GCS resource not found: {e}") from e
    except gcs_exceptions.Forbidden as e:
        logging.error(f"Permission denied when accessing GCS: {e}")
        raise RuntimeError(f"Permission denied when accessing GCS: {e}") from e
    except gcs_exceptions.GoogleAPICallError as e:
        logging.error(f"GCS API error: {e}")
        raise RuntimeError(f"GCS API error: {e}") from e
    except (OSError, IOError) as e:
        logging.error(f"File handling error: {e}")
        raise RuntimeError(f"File handling error: {e}") from e
    except Exception as e:
        logging.error(f"Unexpected error during upload: {e}", exc_info=True)
        raise RuntimeError(f"Unexpected error during upload: {e}") from e

def download_vectorstore_from_gcs(bucket_name: str, prefix: str) -> str:
    """
    Downloads a vector store from GCS to a temporary local folder.
    Returns the path to the temp folder.
    """
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    temp_dir = tempfile.mkdtemp()
    
    blobs = bucket.list_blobs(prefix=prefix)
    for blob in blobs:
        rel_path = os.path.relpath(blob.name, prefix)
        local_path = os.path.join(temp_dir, rel_path)
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        blob.download_to_filename(local_path)
    
    return temp_dir

def fixed_size_chunker(document, tokenizer, chunk_size=150, stride=130):
    all_chunks = []
    all_span_annotations = []
    all_metadata = []

    for page_idx, page_text in enumerate(document):
        tokenized = tokenizer(page_text, return_tensors="pt", add_special_tokens=False)
        input_ids = tokenized["input_ids"].squeeze(0)
        tokens = tokenizer.convert_ids_to_tokens(input_ids)

        span_annotations = []
        chunks = []

        for chunk_idx in range(0, len(tokens), stride):
            start = chunk_idx
            end = min(chunk_idx + chunk_size, len(tokens))
            span_annotations.append((start, end))

            chunk_text = tokenizer.convert_tokens_to_string(tokens[start:end])
            chunks.append(chunk_text)

            all_metadata.append({"page_no": page_idx + 1, "chunk_id": len(span_annotations)})

            if end == len(tokens):
                break

        all_chunks.extend(chunks)
        all_span_annotations.extend(span_annotations)

    return all_chunks, all_span_annotations, all_metadata

def document_to_token_embeddings(model, tokenizer, document, batch_size=4096):
    start_time = time.time()
    if batch_size > 8192:
        raise ValueError("Batch size is too large. Please use a batch size of 8192 or less.")

    tokenized = tokenizer(document, return_tensors="pt", truncation=False)
    input_ids = tokenized['input_ids']
    attention_mask = tokenized['attention_mask']

    outputs = []
    seq_len = input_ids.shape[1]

    for start in range(0, seq_len, batch_size):
        end = min(start + batch_size, seq_len)
        batch_input_ids = input_ids[:, start:end]
        batch_attention_mask = attention_mask[:, start:end]

        with torch.no_grad():
            model_output = model(input_ids=batch_input_ids,
                                 attention_mask=batch_attention_mask)
        outputs.append(model_output.last_hidden_state)

    model_output = torch.cat(outputs, dim=1)
    print("Time taken for embeddings:", time.time() - start_time)
    return model_output

def late_chunking(token_embeddings, span_annotations, max_length=2000):
    start_time = time.time()
    pooled_embeddings = []

    # span_annotations is already a flat list of (start, end)
    if max_length is not None:
        span_annotations = [
            (start, min(end, max_length - 1))
            for (start, end) in span_annotations
            if start < (max_length - 1)
        ]

    for start, end in span_annotations:
        if (end - start) >= 1:
            pooled_embeddings.append(
                token_embeddings[0, start:end].mean(dim=0)  # shape: [hidden_dim]
            )

    pooled_embeddings = [emb.detach().cpu().numpy() for emb in pooled_embeddings]

    print("Time taken to compute chunk embeddings:", time.time() - start_time)
    return pooled_embeddings

def build_vectorstore_simple(document, file_name, bucket_name, user_id):
    print("Building vector store...")

    # Create temp folder instead of local permanent folder
    if bucket_name:
        store_dir = tempfile.mkdtemp()
    else:
        store_dir = os.path.join("VectoreStore", file_name)
        os.makedirs(store_dir, exist_ok=True)

    whole_document = " ".join(document)
    chunks, span_annotations, metadata = fixed_size_chunker(document, tokenizer)
    
    token_embeddings = document_to_token_embeddings(model, tokenizer, whole_document)
    chunk_embeddings = late_chunking(token_embeddings, span_annotations)
    
    embeddings_array = np.array(chunk_embeddings)
    dimension = embeddings_array.shape[1]
    index = faiss.IndexFlatIP(dimension)
    faiss.normalize_L2(embeddings_array)
    index.add(embeddings_array)
    
    # Save FAISS index and metadata
    faiss.write_index(index, os.path.join(store_dir, "index.faiss"))
    with open(os.path.join(store_dir, "chunks_metadata.pkl"), "wb") as f:
        pickle.dump({"chunks": chunks, "metadata": metadata}, f)
    
    # Upload to GCS if bucket_name provided
    if bucket_name and user_id:
        dest_prefix = f"{user_id}/{file_name}"
        upload_vectorstore_to_gcs(store_dir, bucket_name, dest_prefix)
        shutil.rmtree(store_dir, ignore_errors=True)
        print(f"Vector store uploaded to gs://{bucket_name}/{dest_prefix}/")

    logging.info("vectorestore created")
    
    return index, chunks, metadata

def similarity_search(query, index, chunks, metadata, k=25):
    """
    Perform similarity search on the FAISS index
    
    Args:
        query: Search query string
        index: FAISS index
        chunks: List of text chunks
        metadata: List of metadata dictionaries
        k: Number of results to return
    
    Returns:
        List of similar documents with scores
    """
    # Embed the query
    inputs = tokenizer(query, return_tensors="pt", truncation=True, padding=True)
    with torch.no_grad():
        outputs = model(**inputs)
    
    # Get query embedding (mean pooling)
    query_embedding = outputs.last_hidden_state.mean(dim=1).squeeze().numpy()
    query_embedding = query_embedding.reshape(1, -1)
    
    # Normalize the query embedding for cosine similarity
    faiss.normalize_L2(query_embedding)
    
    # Search in the index
    scores, indices = index.search(query_embedding, k)
    
    # Prepare results
    results = []
    for i, (score, idx) in enumerate(zip(scores[0], indices[0])):
        if idx < len(chunks) and score > 0.5:  # ensure valid index + threshold
            # Wrap into Document so build_context can handle it
            doc = Document(
                page_content=chunks[idx],
                metadata=metadata[idx] if idx < len(metadata) else {}
            )
            results.append(doc)
    print(results)
    return results

def load_vectorstore_simple(bucket_name, prefix):
    """
    Load vector store. If bucket_name and prefix are provided, download from GCS first.
    """
    if bucket_name and prefix:
        store_path = download_vectorstore_from_gcs(bucket_name, prefix)
    else:
        store_path = prefix  # local path

    index_path = os.path.join(store_path, "index.faiss")
    metadata_path = os.path.join(store_path, "chunks_metadata.pkl")

    index = faiss.read_index(index_path)
    with open(metadata_path, "rb") as f:
        data = pickle.load(f)

    # Clean up temp folder if downloaded from GCS
    if bucket_name:
        shutil.rmtree(store_path, ignore_errors=True)

    return index, data["chunks"], data["metadata"]

def query_with_llm(query, index, chunks, metadata, k=25):
    """Complete RAG pipeline with LLM"""
    # Perform similarity search
    similar_docs = similarity_search(query, index, chunks, metadata, k)
    
    # Prepare context
    context = "\n\n".join([doc["content"] for doc in similar_docs])
    print(context)
    # Generate response using LLM
    response = llm.invoke(prompt.format(context=context, input=query))
    
    return {
        "answer": response.content,
        "source_documents": similar_docs
    }

# if __name__ == "__main__":
    
#     # Option 1: Build new vector store
#     index, chunks, metadata = build_vectorstore_simple("uploads/lic1.pdf","lic1.pdf")
    
#     # Option 2: Load existing vector store
#     # index, chunks, metadata = load_vectorstore_simple()
    
#     # Test similarity search
#     query = "does policy holder can can return the policy and what conditions are applied if he returns the policy? "
    
#     # Just similarity search
#     results = similarity_search(query, index, chunks, metadata, k=25)
#     print("Similarity Search Results:")
#     for i, result in enumerate(results):
#         print(f"{i+1}. Score: {result['score']:.4f}")
#         print(f"   Content: {result['content'][:100]}...")
#         print(f"   Metadata: {result['metadata']}")
#         print()
    
#     # Full RAG pipeline
#     rag_result = query_with_llm(query, index, chunks, metadata)
#     print("LLM Answer:", rag_result["answer"])
#     print("\nSource Documents:")
#     for doc in rag_result["source_documents"]:
#         print(f"- Score: {doc['score']:.4f} | Page: {doc['metadata'].get('page_no', 'N/A')}")
