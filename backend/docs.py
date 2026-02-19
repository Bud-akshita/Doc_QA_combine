from database import db_dependency
from pydantic import BaseModel, Field
from fastapi import APIRouter, status, HTTPException, Depends , UploadFile , File , Form
from fastapi.responses import FileResponse
from fastapi import BackgroundTasks , Query
from models import Documents, ChatHistory
from typing import List
from auth import get_current_user
import os
import shutil
from datetime import datetime,timedelta,time
from googletrans import Translator
import re
import pytz
from google.cloud import storage
import logging
import tempfile
from google.api_core import exceptions as gcs_exceptions
import requests
import numpy as np
import faiss
import pickle

import traceback
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain.chains import create_retrieval_chain
from langchain.schema import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter

from read_file import extract_content
from website_save_vectore import save_vectore
from website_summary import summary
from translation import save_pdf, translate_to_hindi
from extract_clause import extract
from risk_level import find_high_risk_clauses , get_reference_chunk
from smart_reminder import sentences_with_date_entity,call_lm
from ai_insights import AI_INSIGHTS
import redis

router = APIRouter(
    prefix="/documents",
    tags=["documents"]
)

UPLOAD_BUCKET = "my_bucket_upload"
VECTORESTORE_BUCKET ="my_vectorestore_bucket"

embedding_model = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2",model_kwargs={"use_auth_token": os.environ.get("HF_TOKEN")})
groq_api_key = os.environ.get("GROQ_API_KEY1")
llm=ChatGroq(groq_api_key=groq_api_key,model_name="llama-3.1-8b-instant")

REDIS_URL = os.environ.get("REDIS_URL")
r = redis.from_url(REDIS_URL)

class DocumentResponse(BaseModel):
    id: int
    user_id: int
    doc_name: str
    doc_type: str
    uploaded_at: datetime

class ChatHistoryResponse(BaseModel):
    id: int
    user_id: int
    document_id: int
    question: str
    answer: str
    created_at: datetime

class AskQuestionResponse(BaseModel):
    answer: str
    chat: ChatHistoryResponse 
    ref_map: dict  

    class Config:
        from_attributes = True

class ChatHistoryWithDocumentResponse(BaseModel):
    id: int
    user_id: int
    document_id: int
    question: str
    answer: str
    created_at: datetime
    doc_name: str = Field(..., description="Name of the document")

    class Config:
        from_attributes = True

    @classmethod
    def from_orm(cls, obj):
        return cls(
            id=obj.id,
            user_id=obj.user_id,
            document_id=obj.document_id,
            question=obj.question,
            answer=obj.answer,
            created_at=obj.created_at,
            doc_name=obj.document.doc_name if obj.document else "Unknown"
        )
    
class EmailRequest(BaseModel):
    date: str       
    days: int        
    subject: str

def upload_to_gcs(file: UploadFile, destination_blob_name: str):
    try:
        client = storage.Client()
        bucket = client.bucket(UPLOAD_BUCKET)
        blob = bucket.blob(destination_blob_name)

        # Save file temporarily before uploading to GCS
        tmp_path = f"/tmp/{file.filename}"
        with open(tmp_path, "wb") as buffer:
            buffer.write(file.file.read())

        blob.upload_from_filename(tmp_path)

        return f"gs://{UPLOAD_BUCKET}/{destination_blob_name}"

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

def download_from_gcs(user_id: int, file_name: str) -> str:
    """Download a file from GCS to /tmp and return local path"""
    client = storage.Client()
    bucket = client.bucket(UPLOAD_BUCKET)
    blob = bucket.blob(f"{user_id}/{file_name}")

    tmp_path = os.path.join(tempfile.gettempdir(), file_name)
    blob.download_to_filename(tmp_path)
    return tmp_path

def delete_from_gcs(user_id: int, file_name: str):
    """Delete file from GCS"""
    client = storage.Client()
    bucket = client.bucket(UPLOAD_BUCKET)
    blob = bucket.blob(f"{user_id}/{file_name}")
    blob.delete()

def download_vectore_from_gcs(user_id: str, file_name: str, VECTORESTORE_BUCKET: str = VECTORESTORE_BUCKET, cache_dir: str = "/tmp"):
    """
    Loads FAISS index and docs either from local cache or downloads them from Google Cloud Storage.
    """
    # Define cache paths
    local_dir = os.path.join(cache_dir, str(user_id), file_name)
    os.makedirs(local_dir, exist_ok=True)
    
    index_path = os.path.join(local_dir, "index.faiss")
    docs_path = os.path.join(local_dir, "docs.pkl")

    # If files are already cached locally, load and return them
    if os.path.exists(index_path) and os.path.exists(docs_path):
        print(f"✅ Loaded from cache: {local_dir}")
        index = faiss.read_index(index_path)
        with open(docs_path, "rb") as f:
            docs = pickle.load(f)
        return index, docs

    # Otherwise, download from GCS
    print(f"⬇️ Downloading index and docs from GCS for {user_id}/{file_name} ...")

    client = storage.Client()
    bucket = client.bucket(VECTORESTORE_BUCKET)

    # Define GCS paths
    index_blob_name = f"{user_id}/{file_name}/index.faiss"
    docs_blob_name = f"{user_id}/{file_name}/docs.pkl"

    # Download index file
    index_blob = bucket.blob(index_blob_name)
    docs_blob = bucket.blob(docs_blob_name)

    if not index_blob.exists() or not docs_blob.exists():
        raise FileNotFoundError(f"❌ index.faiss or docs.pkl not found in gs://{VECTORESTORE_BUCKET}/{user_id}/{file_name}/")

    index_blob.download_to_filename(index_path)
    docs_blob.download_to_filename(docs_path)

    # Load into memory
    index = faiss.read_index(index_path)
    with open(docs_path, "rb") as f:
        docs = pickle.load(f)

    print(f"✅ Downloaded and cached at {local_dir}")

    return index, docs

def chunk_documents(page_texts, chunk_size=1200, chunk_overlap=200):
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ".", "!", "?", ",", " ", ""]
    )
    docs = []
    for page_no, page_text in enumerate(page_texts, start=1):
        chunks = text_splitter.split_text(page_text)
        for i, chunk in enumerate(chunks):
            docs.append(
                Document(
                    page_content=chunk,
                    metadata={"page_no": page_no, "chunk_id": i}
                )
            )
    return docs

def build_faiss_index(user_id, file_name, docs, embeddings, space='cosine', M=16, efConstruction=40):
    """
    docs: list of langchain Documents
    embeddings: list or array of vector embeddings
    space: 'cosine' or 'l2'
    """
    texts = [doc.page_content for doc in docs]
    vecs = np.array(embedding_model.embed_documents(texts)).astype('float32')

    dim = vecs.shape[1]

    # --- choose distance metric ---
    if space == 'cosine':
        # normalize vectors for cosine similarity
        faiss.normalize_L2(vecs)
        index = faiss.IndexHNSWFlat(dim, M, faiss.METRIC_INNER_PRODUCT)
    else:
        index = faiss.IndexHNSWFlat(dim, M, faiss.METRIC_L2)

    # Set efConstruction parameter
    index.hnsw.efConstruction = efConstruction

    # Add vectors to index
    index.add(vecs)

    store_dir = "/tmp"
    os.makedirs(store_dir, exist_ok=True)

    faiss_index_path = os.path.join(store_dir, "index.faiss")
    docs_path = os.path.join(store_dir, "docs.pkl")

    faiss.write_index(index, faiss_index_path)
    with open(docs_path, "wb") as f:
        pickle.dump(docs, f)

    # Upload to GCS if needed
    dest_prefix = f"{user_id}/{file_name}"
    client = storage.Client()
    bucket = client.bucket(VECTORESTORE_BUCKET)
    
    index_blob_name = f"{dest_prefix}/index.faiss"
    index_blob = bucket.blob(index_blob_name)
    index_blob.upload_from_filename(faiss_index_path)

    # Upload docs file
    docs_blob_name = f"{dest_prefix}/docs.pkl"
    docs_blob = bucket.blob(docs_blob_name)
    docs_blob.upload_from_filename(docs_path)

    # Clean up local temp files
    shutil.rmtree(store_dir, ignore_errors=True)
    print(f"Vector store uploaded to gs://{VECTORESTORE_BUCKET}/{dest_prefix}/")
    return index, docs

# def chunk_text(text, max_words=150, overlap=20):
#     words = text.split()
#     chunks = []
#     i = 0
#     while i < len(words):
#         chunk = words[i:i+max_words]
#         chunks.append(" ".join(chunk))
#         i += max_words - overlap  
#     return chunks

@router.get("/", response_model=List[DocumentResponse])
async def get_docs(db: db_dependency, user: dict = Depends(get_current_user)):
    docs = db.query(Documents).filter(Documents.user_id == user["id"]).order_by(Documents.id.desc()).all()
    if not docs:
        raise HTTPException(status_code=404, detail="No documents found for this user")
    return docs

@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_doc(
    db: db_dependency,
    file: UploadFile = File(...),                 
    doc_type: str = Form(...),            
    user: dict = Depends(get_current_user)
):
    try:
        file_name = file.filename

        existing_doc = db.query(Documents).filter(
            Documents.user_id == user["id"],
            Documents.doc_name == file_name
        ).first()

        if existing_doc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You have already uploaded this file."
            )
        # Upload file directly to GCS
        gcs_uri = upload_to_gcs(file, f"{user['id']}/{file_name}")

        # Save in database
        new_doc = Documents(
            user_id=user["id"],
            doc_name=file_name,
            doc_type=doc_type
        )
        db.add(new_doc)
        db.commit()
        db.refresh(new_doc)

        tmp_path = f"/tmp/{file.filename}"
        document = extract_content(tmp_path)
        docs = chunk_documents(document)
        embeddings_array = [embedding_model.embed_query(doc.page_content) for doc in docs]
        build_faiss_index(user["id"],file_name,docs, embeddings_array, space='cosine')
        # build_vectorstore_simple(document, file_name,VECTORESTORE_BUCKET,user["id"])

        return new_doc
    
    except Exception as e:
        logging.error("failed : {}",e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"failed to upload : {str(e)}"
        )

def delete_vectore_from_gcs(user_id: int, file_name: str, bucket_name: str = VECTORESTORE_BUCKET):
    """Delete vectorstore files from GCS"""
    try:
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        
        # Define the prefix for all vectorstore files
        prefix = f"{user_id}/{file_name}/"
        
        # List and delete all blobs with this prefix
        blobs = bucket.list_blobs(prefix=prefix)
        
        deleted_count = 0
        for blob in blobs:
            blob.delete()
            deleted_count += 1
            print(f"Deleted {blob.name} from vectorstore bucket")
        
        print(f"Deleted {deleted_count} vectorstore files for {user_id}/{file_name}")
        return deleted_count
        
    except Exception as e:
        logging.error(f"Error deleting vectorstore from GCS: {e}")
        raise RuntimeError(f"Failed to delete vectorstore: {str(e)}")

def cleanup_risk_data(user_id: int, file_name: str):
    """Clean up in-memory risk data for the document"""
    try:
        # Clean up risk_results
        risk_key = (user_id, file_name)
        if risk_key in risk_results:
            del risk_results[risk_key]
            print(f"Cleaned up risk_results for {risk_key}")
        
        # Clean up risk_vectors
        if risk_key in risk_vectors:
            del risk_vectors[risk_key]
            print(f"Cleaned up risk_vectors for {risk_key}")
        
        # Also clean any related files in risk analysis
        cleanup_risk_files(user_id, file_name)
        
        return True
        
    except Exception as e:
        logging.error(f"Error cleaning up risk data: {e}")
        return False

def cleanup_risk_files(user_id: int, file_name: str):
    """Clean up any risk analysis files from GCS"""
    try:
        client = storage.Client()
        bucket = client.bucket(UPLOAD_BUCKET)  # or create a separate risk bucket if needed
        
        # Clean up extracted clauses file if it exists
        clauses_blob_name = f"{user_id}/{file_name}/clean.json"
        clauses_blob = bucket.blob(clauses_blob_name)
        if clauses_blob.exists():
            clauses_blob.delete()
            print(f"Deleted risk clauses file: {clauses_blob_name}")
                
    except Exception as e:
        logging.error(f"Error cleaning up risk files: {e}")

def cleanup_local_cache(user_id: int, file_name: str, cache_dir: str = "/tmp"):
    """Clean up local cached vectorstore files"""
    try:
        local_dir = os.path.join(cache_dir, str(user_id), file_name)
        if os.path.exists(local_dir):
            shutil.rmtree(local_dir)
            print(f"Cleaned up local cache: {local_dir}")
        return True
    except Exception as e:
        logging.error(f"Error cleaning local cache: {e}")
        return False

@router.delete("/delete")
async def delete_doc(doc_name: str, doc_type: str, db: db_dependency, user: dict = Depends(get_current_user)):
    document = (
        db.query(Documents)
        .filter(
            Documents.doc_name == doc_name,
            Documents.doc_type == doc_type,
            Documents.user_id == user['id']
        )
        .first()
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found or not owned by user")

    try:
        # Delete from GCS (upload bucket)
        delete_from_gcs(user["id"], doc_name)

        # Delete vectorstore from GCS
        delete_vectore_from_gcs(user["id"], doc_name)

        # Clean up local cache
        cleanup_local_cache(user["id"], doc_name)

        # Clean up in-memory risk data
        cleanup_risk_data(user["id"], doc_name)

        # Delete from database
        db.delete(document)
        db.commit()

        return {"message": f"Document '{doc_name}' deleted successfully from all storage locations"}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error during deletion: {str(e)}")

def retrieve_best_chunks_web(question, vectorstore, top_k=12):
    results = vectorstore.similarity_search_with_score(question, k=top_k)
    print("length of result:", len(results))

    filtered_docs = []
    # score comes between 0 to 2  0 means similar 2 means opposite
    for i, (doc, score) in enumerate(results):
        print(score)
        if score <= 1.7 :
            print(f"\n--- Chunk {i+1} ---")
            print("score:", score)
            print("Content:", doc.page_content[:200], "...")
            print("Metadata:", doc.metadata)
            filtered_docs.append(doc)

    return filtered_docs
    
def retrieve_best_chunks(index, query_embedding, docs, k=12, efSearch=50, space='cosine'):
    query_vec = np.array(query_embedding).astype('float32').reshape(1, -1)
    if space == 'cosine':
        faiss.normalize_L2(query_vec)

    index.hnsw.efSearch = efSearch
    D, I = index.search(query_vec, k)  # D = distances, I = indices

    results = []
    for dist, idx in zip(D[0], I[0]):
        doc = docs[idx]
        # convert distance to similarity if cosine
        score = dist  # higher = more similar (since using inner product)
        if score >= 0.2 :
            results.append(doc)
    return results

def build_context(chunks):
    context = []
    chunk_map = {}
    ref_map = {}
    i=0
    for chunk in chunks:
        m = chunk.metadata
        ref = f"pg{m.get('page_no',0)}c{m.get('chunk_id',0)}"
        i=i+1
        chunk_map[f"REF:{ref}"] = i
        ref_map[i] = [chunk.page_content, m.get('page_no',0)]
        context.append(f"[REF:{ref}]\n{chunk.page_content}\n[/REF]")

    return "\n".join(context) ,chunk_map, ref_map 

def build_context_web(chunks):
    context = []
    chunk_map = {}
    ref_map = {}
    i =0
    for chunk in chunks:
        m = chunk.metadata
        url = m.get('primary_url')
        i = i+1
        chunk_map[f"URL:{url}"] = i
        ref_map[i] = [chunk.page_content,url]
        context.append(f"[URL:{url}]{chunk.page_content}\n[/URL]")
    return "\n".join(context), chunk_map, ref_map

def replace_refs(text, chunk_map):
    result = re.sub(
    r"[\(\[]REF:[^\)\]]+[\)\]]", 
    lambda m: f"({chunk_map.get(m.group(0)[1:-1], m.group(0))})", 
    text)
    return result

def replace_refs_web(text,chunk_map):
    result = re.sub(
    r"[\(\[]URL:[^\)\]]+[\)\]]", 
    lambda m: f"({chunk_map.get(m.group(0)[1:-1], m.group(0))})", 
    text)
    return result

# def validate_reference(response, valid_refs):
#     """Ensure only valid references are used"""
#     found_refs = re.findall(r'\[REF:pg\d+c\d+\]', response)
#     for ref in found_refs:
#         if ref not in valid_refs:
#             # Flag hallucinated reference
#             response = response.replace(ref, "")
#     return response

@router.post("/ask-question",response_model=AskQuestionResponse)
async def ask_question(db: db_dependency,filename: str = Form(...),document_type: str = Form(...),question: str = Form(...), user: dict = Depends(get_current_user)):
    
    if document_type =="website":

        prompt=ChatPromptTemplate.from_template(
            """
            Answer the questions based on the provided context only.
            Please provide the most accurate response based on the question and context. 
            <context>
            {context}
            <context>
            Questions:{input}
            For every response include the URL tag(s) at the END of the sentence.
            Whenever you include a URL, format it strictly as [URL:https://example.com/abc]
            """
        )
        
        file_path = download_from_gcs(user["id"], filename)
        vectors=save_vectore(file_path)
        best_chunks = retrieve_best_chunks_web(question, vectors)
        context, chunk_map, ref_map= build_context_web(best_chunks)
        print(ref_map)
        final_prompt = prompt.format(context=context, input=question)
        response = llm.invoke(final_prompt)
        result = response.content
        answer = replace_refs_web(result,chunk_map)

        doc = db.query(Documents).filter(Documents.doc_name == filename).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        chat_history = ChatHistory(
            user_id = user["id"],
            document_id = doc.id,
            question = question,
            answer = answer, 
        )
        db.add(chat_history)
        db.commit()
        db.refresh(chat_history)

        return {
            "answer":answer,
            "chat": chat_history,
            "ref_map": ref_map
        }
    
    else : 
        try:       

            prompt=ChatPromptTemplate.from_template(
            """
            You are a helpful and precise assistant for answering questions about financial documents. Use **only** the provided document text to answer the questions. 
            If the answer is not found in the document, state 'The document does not specify.' Do not speculate or use outside knowledge. For numerical questions, provide the exact figure. For conditional questions, quote the relevant clause.
 
            **Document Context:**
            - **Type:** {doc_type}
            - **Text:** {document_text}
            
            **User Question:** {user_question}
            
            **Instructions for Answering:**
            1.  Analyze the user's question.
            2.  Search the document text for information that directly answers it.
            3.  Formulate a direct, concise answer.
            4.  cite the sourcein the answer: Provide a excerpt or reference the section (e.g., 'As per Section 4.1...') that supports your answer.
            5.  For every response include the REF tag(s) at the END of the sentence as mentioned in the Text.
            6.  Whenever you include a reference, format it strictly as [REF:pgXcY] where X=page number, Y=chunk number
            
            **Answer Format:**

            answer : "Your concise answer to the question.",
            confidence : "High" | "Medium" | "Low" | "Not Found"
            """
            )
            index , docs = download_vectore_from_gcs(user["id"],filename)
            query_emb = embedding_model.embed_query(question)
            best_chunks = retrieve_best_chunks(index, query_emb, docs, k=12, efSearch=16, space='cosine')

            context, chunk_map, ref_map= build_context(best_chunks)
            print(ref_map)
            final_prompt = prompt.format(doc_type=document_type,document_text=context, user_question=question)
            response = llm.invoke(final_prompt)
            result = response.content
            answer = replace_refs(result,chunk_map)
            
            doc = db.query(Documents).filter(Documents.doc_name == filename).first()
            if not doc:
                raise HTTPException(status_code=404, detail="Document not found")

            chat_history = ChatHistory(
                user_id = user["id"],
                document_id = doc.id,
                question = question,
                answer = answer, 
            )
            db.add(chat_history)
            db.commit()
            db.refresh(chat_history)

            return {
                "answer":answer,
                "chat": chat_history,
                "ref_map": ref_map
            }
        except FileNotFoundError as e:
            logging.error(f"File not found: {e}")
            raise HTTPException(status_code=404, detail=f"File not found: {str(e)}")

        except ConnectionError as e:
            logging.error(f"Connection error: {e}")
            raise HTTPException(status_code=503, detail="Service unavailable, please retry later")

        except ValueError as e:
            logging.error(f"Value error: {e}")
            raise HTTPException(status_code=400, detail=f"Bad input: {str(e)}")
        
        except HTTPException as e:
            # Log traceback to console for debugging
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"Failed to process file: {str(e)}")
        
        except Exception as e:
            logging.error(f"Unexpected error: {e}")
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"Unexpected server error: {str(e)}")
    
@router.get("/history/{document_name}", response_model=List[ChatHistoryWithDocumentResponse])
async def get_chat_history_by_document(
    document_name: str,
    db: db_dependency,
    user: dict = Depends(get_current_user)
):
    history = db.query(ChatHistory).join(Documents).filter(
        ChatHistory.user_id == user["id"],
        Documents.doc_name == document_name
    ).order_by(ChatHistory.created_at.desc()).all()
    
    if not history:
        raise HTTPException(
            status_code=404, 
            detail=f"No chat history found for document '{document_name}'"
        )
    
    return [ChatHistoryWithDocumentResponse.from_orm(h) for h in history]

@router.post("/summary")
async def generate_summary(filename :str = Form(...),document_type: str = Form(...), user:dict =Depends(get_current_user)):
    file_path = download_from_gcs(user["id"], filename)
    
    if document_type=='website':
        vectorstore = save_vectore(file_path)
        answer = summary(vectorstore)
        return {"summary":answer}

    elif document_type=='loan':
        content = extract_content(file_path)

        # loan_config_url = os.environ.get("LOAN_CONFIG_URL")

        # response = requests.get(loan_config_url)

        # if response.status_code == 200:
        #     loan_config = response.json()  # directly parse JSON
        #     print(loan_config)
        # else:
        #     print(f"Failed to fetch JSON. Status code: {response.status_code}")

        prompt = ChatPromptTemplate.from_template(
        """                
            You are a helpful and precise assistant for summarizing financial documents.  
            Please provide the most accurate and concise response based on the given document and questions.  
            If the answer is not found in the document, clearly state that the document does not specify it — rephrasing naturally based on the question.

            <context>
            {doc_type}
            {context}
            </context>

            Title : {title}
            Questions: {input}

            ### Instructions for generating output:

            1. For each question, return output in this exact format:
            <Title>: <Answer (1–3 lines)>

            2. Do not use labels such as “Title:” or “Answer:”.
            3. Write the title and the answer on the same line, separated by a colon.
            4. If a detail is missing, rewrite “The document does not specify” naturally to fit the question.
            5. Keep answers concise, factual, and easy to read — no lists, bullets, or explanations.

            """
        )
        index, docs = download_vectore_from_gcs(user["id"],filename)

        subcategory_prompt = ChatPromptTemplate.from_template("""
        question : what is the type of the loan (ex: personal,edication,microfinance,mortage,gold,vehicle,business,credit card) if no one from provided e.x return default.
        Strictly, provide one word answer from the given context. context {input} 
        """)
        input = " ".join(doc.page_content for doc in docs[:4])
        final_sub_prompt = subcategory_prompt.format(input=input)
        response = llm.invoke(final_sub_prompt)
        subcategory= response.content

        all_answer = []
        for key, qes in AI_INSIGHTS["loan"][subcategory.lower()]:
            title = key
            questions = qes

            query_emb = embedding_model.embed_query(questions)
            best_chunks = retrieve_best_chunks(index, query_emb, docs, k=12, efSearch=16, space='cosine')
            context = "\n".join([chunk.page_content for chunk in best_chunks])
            final_prompt = prompt.format(doc_type=document_type,context=context, title =title, input=questions)
            response = llm.invoke(final_prompt)
            result = response.content
            all_answer.append(result)

        # for section in loan_config["loan"].values():
        #     title = section["title"]
        #     questions = ", ".join(section["questions"])

        #     query_emb = embedding_model.embed_query(questions)
        #     best_chunks = retrieve_best_chunks(index, query_emb, docs, k=12, efSearch=16, space='cosine')
        #     context = "\n".join([chunk.page_content for chunk in best_chunks])
        #     final_prompt = prompt.format(doc_type=document_type,context=context, title =title, input=questions)
        #     response = llm.invoke(final_prompt)
        #     result = response.content
        #     all_answer.append(result)

        answer = "\n".join(all_answer)

        return {"summary": answer}
    else:
        try:       
            prompt = ChatPromptTemplate.from_template(
                """
                Summarize and give the all important details mentioned in the Query Based on provided context only  
                <context>
                {context}
                <context>
                Query:{input}
                """
            )
            vectors = download_vectore_from_gcs(user["id"],filename)
            index, docs = download_vectore_from_gcs(user["id"],filename)
            vectors = FAISS.from_documents(docs, embedding_model)
            document_chain = create_stuff_documents_chain(llm, prompt)
            retriever = vectors.as_retriever()
            retrieval_chain = create_retrieval_chain(retriever, document_chain)

            queries = {
                "insurance": """Document Type:
                    Document Name:
                    Date Issued:
                    Issued By:
                    Policy no:
                    Premiun Amount:
                    Type of Coverage:
                    Coverage Amount:
                    Deductible:
                    Exclusions:
                    Claims Process:
                    Beneficiaries:
                    Policy Term:
                    Renewal Conditions:
                    Exclusions and Limitations:
                    Cancellation Policy:
                    Contact Information for Filing a Claim:
                    Contact Information for Making Policy Changes:""",
                
                # "loan": """Document Type:
                #     Document Name:
                #     Date Issued:
                #     Issued By:
                #     Amount Borrowed:
                #     Interest Rate:
                #     Loan Term:
                #     Repayment Schedule:
                #     Prepayment Penalties:
                #     Late Fees:
                #     Default Terms:
                #     Customer Service Contact Information:
                #     Rights and Obligations:
                #     Disbursement Details:
                #     Grace Period:""",
                
                "credit_card_terms": """Document Type:
                    Document Name:
                    Date Issued:
                    Issued By:
                    Interest rate:
                    Annual purchase rate:
                    Fees:
                    Credit Limit & Cash Advance Limit:
                    Grace Period:
                    Billing & Payment:
                    Rewards & Benefits:
                    Statement Date:
                    Due Date:
                    Grace period end date:
                    Annual feed charge Date:""",
                
                "tenders": """Document Type:
                    Document Name:
                    Date Issued:
                    Tender issue Date:
                    Clarification/Query Deadline:
                    Bid submission deadline:
                    Bid Opening Date:
                    Contract Start Date:
                    Contract Duration and completion Date:
                    Validity period of Bid:
                    Eligibility criteria:
                    Deliverables:
                    Submission requirement:
                    Evalution criteria:
                    Financial information:
                    Compliance and legal terms:""",
                
                "other": """Document Type:
                    Document Name:
                    Date of Document:
                    Issuing Authority/Organization:
                    Purpose of Document:
                    Key Parties Involved:
                    Main Subject/Topic:
                    Key Terms and Definitions:
                    Important Dates or Deadlines:
                    Financial Information (if any):
                    Legal Implications (if any):
                    Obligations or Responsibilities:
                    Rights or Benefits:
                    Conditions or Requirements:
                    Consequences or Penalties:
                    Amendment or Termination Clauses:
                    Dispute Resolution Process:
                    Contact Information:
                    Additional Notes or Special Provisions:"""
            }

            summary_query = queries.get(document_type, queries["other"])

            response = retrieval_chain.invoke({"input": summary_query})
            answer = response["answer"].replace("**", "")

            return {"summary": answer}

        except FileNotFoundError as e:
            logging.error(f"File not found: {e}")
            raise HTTPException(status_code=404, detail="Source file not found")

        except KeyError as e:
            logging.error(f"Missing key in response: {e}")
            raise HTTPException(status_code=500, detail=f"Response format error: missing {str(e)}")

        except ValueError as e:
            logging.error(f"Value error: {e}")
            raise HTTPException(status_code=400, detail=f"Bad data: {str(e)}")

        except ConnectionError as e:
            logging.error(f"Connection error: {e}")
            raise HTTPException(status_code=503, detail="Service unavailable, please retry later")

        except HTTPException as e:  
            raise HTTPException(status_code=500, detail=str(e))
        
        except Exception as e:
            logging.error("Unexpected error occurred: {e}")
            raise HTTPException(status_code=500, detail="Unexpected server error")
    
@router.post("/ask-question-hi")
async def ask_question_hindi(
    db: db_dependency,
    filename: str = Form(...),
    document_type: str = Form(...),
    question: str = Form(...),
    user: dict = Depends(get_current_user)
):
    # Step 1: Translate question from Hindi to English
    translator = Translator()
    try:
        english_question = translator.translate(question, src="hi", dest="en").text
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Translation failed: {str(e)}")
    
    try:
        if document_type == "website":
            file_path = download_from_gcs(user["id"], filename)

            prompt=ChatPromptTemplate.from_template(
            """
            Answer the questions based on the provided context only.
            Please provide the most accurate response based on the question and context. 
            <context>
            {context}
            <context>
            Questions:{input}
            For every response include the URL tag(s) at the END of the sentence.
            Whenever you include a URL, format it strictly as [URL:https://example.com/abc]
            """
            )
            
            index , docs = download_vectore_from_gcs(user["id"],filename)
            query_emb = embedding_model.embed_query(question)
            best_chunks = retrieve_best_chunks(index, query_emb, docs, k=12, efSearch=16, space='cosine')

            context, chunk_map, ref_map= build_context(best_chunks)
            print(ref_map)
            final_prompt = prompt.format(context=context, input=question)
            response = llm.invoke(final_prompt)
            result = response.content
            answer = replace_refs(result,chunk_map)

            hindi_answer = translator.translate(answer, src="en", dest="hi").text
            
            # Save to database
            doc = db.query(Documents).filter(Documents.doc_name == filename).first()
            if not doc:
                raise HTTPException(status_code=404, detail="Document not found")
            
            chat_history = ChatHistory(
                user_id=user["id"],
                document_id=doc.id,
                question=question,  # Store original Hindi question
                answer=hindi_answer  # Store Hindi answer
            )
            db.add(chat_history)
            db.commit()
            db.refresh(chat_history)
            
            return {
                "question_hindi": question,
                "question_english": english_question,
                "answer_english": answer,
                "answer_hindi": hindi_answer,
                "chat_id": chat_history.id,
                "ref_map": ref_map
            }

        else:
            prompt = ChatPromptTemplate.from_template(
                """
            You are a helpful and precise assistant for answering questions about financial documents. Use **only** the provided document text to answer the questions. 
            If the answer is not found in the document, state 'The document does not specify.' Do not speculate or use outside knowledge. For numerical questions, provide the exact figure. For conditional questions, quote the relevant clause.
 
            **Document Context:**
            - **Type:** {doc_type}
            - **Text:** {document_text}
            
            **User Question:** {user_question}
            
            **Instructions for Answering:**
            1.  Analyze the user's question.
            2.  Search the document text for information that directly answers it.
            3.  Formulate a direct, concise answer.
            4.  cite the source: Provide a excerpt or reference the section (e.g., 'As per Section 4.1...') that supports your answer.
            5.  For every response include the REF tag(s) at the END of the sentence.
            6.  Whenever you include a reference, format it strictly as [REF:pgXcY]
            
            **Answer Format:**

            "question": "[The user's question]",
            "answer": "Your concise answer to the question.",
            "confidence": "High" | "Medium" | "Low" | "Not Found"
            """
            )
            
            # store_path = download_vectore_from_gcs(user["id"], filename)
            index, chunks, metadata = load_vectorstore_simple(VECTORESTORE_BUCKET,prefix=f"{user['id']}/{filename}/")
            # Optionally, delete temp folder after loading
            # shutil.rmtree(store_path, ignore_errors=True)
            results = similarity_search(question, index, chunks, metadata, k=12)
            print(metadata)
            context, chunk_map, ref_map= build_context(results)    
            final_prompt = prompt.format(doc_type=document_type,document_text=context, user_question=english_question)
            response = llm.invoke(final_prompt)
            result = response.content
            print(result)
            answer = replace_refs(result,chunk_map)
            
            # Step 3: Translate answer to Hindi
            hindi_answer = translator.translate(answer, src="en", dest="hi").text
            
            # Save to database
            doc = db.query(Documents).filter(Documents.doc_name == filename).first()
            if not doc:
                raise HTTPException(status_code=404, detail="Document not found")
            
            chat_history = ChatHistory(
                user_id=user["id"],
                document_id=doc.id,
                question=question,  # Store original Hindi question
                answer=hindi_answer  # Store Hindi answer
            )
            db.add(chat_history)
            db.commit()
            db.refresh(chat_history)
            
            return {
                "question_hindi": question,
                "question_english": english_question,
                "answer_english": answer,
                "answer_hindi": hindi_answer,
                "chat_id": chat_history.id,
                "ref_map": ref_map
            }
        
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to process: {str(e)}")

@router.post("/translate/{filename}")
async def translate_file(filename: str):
    """Translate a document in uploads folder into Hindi and return as downloadable PDF."""
    try:
        file_path = download_from_gcs(user["id"], filename)
    except Exception:
        raise HTTPException(status_code=404, detail="File not found in GCS")

    try:
        # Extract text (list of text chunks from the file)
        contents = extract_content(file_path)

        hindi_translations = []
        for text_block in contents:
            translated = translate_to_hindi(text_block)
            hindi_translations.append(translated)

        # Combine into one big text
        final_text = "\n\n".join(hindi_translations)

        # Save to PDF
        output_pdf = os.path.splitext(filename)[0] + "_hindi.pdf"
        output_path = download_from_gcs(user["id"], output_pdf)
        save_pdf(final_text, output_path)

        # Return file for download
        return FileResponse(
            output_path,
            media_type="application/pdf",
            filename=output_pdf
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
risk_results = {}
risk_vectors = {}

def run_high_risk(filename: str, doc_type: str,user):

    file_path = download_from_gcs(user["id"], filename)
    content = extract_content(file_path)

    index, risk_vectors[(user["id"], filename)] = download_vectore_from_gcs(user["id"],filename)
    extract(risk_vectors[(user["id"], filename)],user["id"],filename)
    high_risk_clauses = find_high_risk_clauses(doc_type,user["id"],filename)

    risk_results[(user["id"], filename)] = high_risk_clauses


@router.post("/high-risk-start")
async def start_high_risk(
    filename: str = Form(...),
    doc_type: str = Form(...),
    user: dict = Depends(get_current_user),
    background_tasks: BackgroundTasks = None
):
    if doc_type != "website":
        background_tasks.add_task(run_high_risk, filename, doc_type,user)
        return {"status": "processing", "message": f"High risk analysis started for {filename}"}


@router.get("/high-risk-result/{filename:path}")
async def get_high_risk_result(
    filename: str,
    doc_type: str = Query(...),  # <- doc_type comes from frontend
    user: dict = Depends(get_current_user)
):
    if doc_type != "website":
        key = (user["id"], filename)

        if key not in risk_results:
            # Check if file is actually finished in GCS
            storage_client = storage.Client()
            bucket = storage_client.bucket("my_bucket_upload")
            blob = bucket.blob(f"{user['id']}/{filename}/clean.json")

            if blob.exists():
                # File is done but memory was cleared
                high_risk_clauses = find_high_risk_clauses(doc_type, user["id"],filename)
                risk_results[key] = high_risk_clauses
                return {"status": "done", "high_risk_clauses": high_risk_clauses}

            # Restart the background job
            background_tasks = BackgroundTasks()
            background_tasks.add_task(run_high_risk, filename, doc_type, user)
            return {"status": "restarted", "message": "Previous task lost; restarting analysis."}

        return {"status": "done", "high_risk_clauses": risk_results[key]}
        
@router.get("/get-reference/{filename}/{ref}")
async def get_reference(filename: str, ref: str, user: dict = Depends(get_current_user)):

    try:
        key = (user["id"], filename) 
        vector = risk_vectors.get(key)
        if not vector:
            raise HTTPException(status_code=404, detail="No risk vectors found for this file")
        reference_info = get_reference_chunk(vector, ref)

        return{
            "success": True,
            "reference": ref,
            "reference_info": reference_info
        }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving reference: {str(e)}")

@router.post("/smart-reminder")
async def extract_dates(filename: str = Form(...),doc_type: str = Form(...),user: dict = Depends(get_current_user)):

    file_path = download_from_gcs(user["id"], filename)
    try:
        page_texts = extract_content(file_path)
        page_texts = "\n".join(page_texts)
        sentences_with_date = sentences_with_date_entity(page_texts)
        response = call_lm(sentences_with_date,doc_type)

        return {"status": "success", "data": response}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

@router.post("/schedule-email")
async def schedule_email(req: EmailRequest, user: dict = Depends(get_current_user)):
    try:
        # Parse date (dd-mm-yyyy)
        event_date = datetime.strptime(req.date, "%d-%m-%Y")
        formatted_date = event_date.strftime("%d-%b-%Y")

        # Set fixed time 
        fixed_time = time(15,10)  
        event_datetime = datetime.combine(event_date, fixed_time)

        # Subtract days
        send_datetime = event_datetime - timedelta(days=req.days)

        # Localize to IST
        ist = pytz.timezone("Asia/Kolkata")
        send_datetime = ist.localize(send_datetime)

        # Create body dynamically
        body = f"This is a reminder: {req.subject} on {formatted_date}. " \
               f"We are notifying you {req.days} days before."

        # Generate a unique task ID
        import uuid
        task_id = str(uuid.uuid4())

        # Store task in Redis with timestamp
        task = {
            "task_id": task_id,
            "subject": req.subject,
            "body": body,
            "to_email": user["email"],
            "send_timestamp": send_datetime.timestamp()
        }

        import json
        r.rpush("email_queue", json.dumps(task))

        return {
            "status": "scheduled",
            "task_id": task_id,
            "scheduled_for": send_datetime.strftime("%d-%b-%Y %H:%M:%S")
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}  

@router.delete("/cancel-email/{task_id}")
async def cancel_email(task_id: str):
    import json
    removed = 0
    all_tasks = r.lrange("email_queue", 0, -1)
    
    for task_json in all_tasks:
        task = json.loads(task_json)
        if task.get("task_id") == task_id:
            r.lrem("email_queue", 1, task_json)
            removed += 1

    if removed > 0:
        return {
            "status": "success",
            "message": f"Email task {task_id} has been cancelled",
            "task_id": task_id
        }
    else:
        return {
            "status": "error",
            "message": f"No email task found with id {task_id}",
            "task_id": task_id
        }