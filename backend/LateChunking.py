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

def extract_pdf_with_ocr(file_path):
    start_time = time.time()
    doc = fitz.open(file_path)
    all_docs = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        page_text = page.get_text("text")

        images = page.get_images(full=True)
        ocr_texts = []
        for img_index, img in enumerate(images):
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            image = Image.open(io.BytesIO(image_bytes))
            ocr_text = pytesseract.image_to_string(image)
            if ocr_text.strip():
                ocr_texts.append(ocr_text)

        merged_text = page_text + "\n" + "\n".join(ocr_texts)
        all_docs.append(merged_text.strip())

    if not any(text.strip() for text in all_docs):
        page_texts = []
        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap(dpi=200)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            text = pytesseract.image_to_string(img)
            page_texts.append(text.strip())
        return page_texts 
    print("Time taken to extract text from PDF:", time.time()-start_time)
    return all_docs

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

def build_vectorstore_simple(document,file_name):
    print("Building vector store...")

    store_dir = "VectoreStore/"+file_name
    os.makedirs(store_dir, exist_ok=True)

    # document = extract_pdf_with_ocr(pdf_path)
    whole_document = " ".join(document)
    chunks, span_annotations, metadata = fixed_size_chunker(document, tokenizer)
    
    token_embeddings = document_to_token_embeddings(model, tokenizer, whole_document)
    chunk_embeddings = late_chunking(token_embeddings, span_annotations)
    
    # Convert to numpy array
    embeddings_array = np.array(chunk_embeddings)
    
    # Create FAISS index
    dimension = embeddings_array.shape[1]
    index = faiss.IndexFlatIP(dimension)  # Inner Product for cosine similarity
    faiss.normalize_L2(embeddings_array)  # Normalize for cosine similarity
    index.add(embeddings_array)
    
    # Save index and data
    faiss.write_index(index, f"{store_dir}/index.faiss")
    
    with open(os.path.join(store_dir, "chunks_metadata.pkl"), "wb") as f:
        pickle.dump({"chunks": chunks, "metadata": metadata}, f)
    
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

def load_vectorstore_simple(store_path):
    """Load the saved vector store"""
    index_path = store_path+ "/index.faiss"
    metadata_path = store_path+ "/chunks_metadata.pkl"
    
    # load FAISS index
    index = faiss.read_index(index_path)
    
    # load metadata
    with open(metadata_path, "rb") as f:
        data = pickle.load(f)
    
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

if __name__ == "__main__":
    
    # Option 1: Build new vector store
    index, chunks, metadata = build_vectorstore_simple("uploads/lic1.pdf","lic1.pdf")
    
    # Option 2: Load existing vector store
    # index, chunks, metadata = load_vectorstore_simple()
    
    # Test similarity search
    query = "does policy holder can can return the policy and what conditions are applied if he returns the policy? "
    
    # Just similarity search
    results = similarity_search(query, index, chunks, metadata, k=25)
    print("Similarity Search Results:")
    for i, result in enumerate(results):
        print(f"{i+1}. Score: {result['score']:.4f}")
        print(f"   Content: {result['content'][:100]}...")
        print(f"   Metadata: {result['metadata']}")
        print()
    
    # Full RAG pipeline
    rag_result = query_with_llm(query, index, chunks, metadata)
    print("LLM Answer:", rag_result["answer"])
    print("\nSource Documents:")
    for doc in rag_result["source_documents"]:
        print(f"- Score: {doc['score']:.4f} | Page: {doc['metadata'].get('page_no', 'N/A')}")