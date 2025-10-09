from database import db_dependency
from pydantic import BaseModel, Field
from fastapi import APIRouter, status, HTTPException, Depends , UploadFile , File , Form
from fastapi.responses import FileResponse
from fastapi import BackgroundTasks
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

import traceback
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain.chains import create_retrieval_chain
from langchain.schema import Document

from read_file import extract_content
from website_save_vectore import save_vectore
from website_summary import summary
from translation import save_pdf, translate_to_hindi
from extract_clause import extract
from risk_level import find_high_risk_clauses , get_reference_chunk
from smart_reminder import sentences_with_date_entity,call_lm
from LateChunking import build_vectorstore_simple, load_vectorstore_simple, similarity_search
import redis

router = APIRouter(
    prefix="/documents",
    tags=["documents"]
)

UPLOAD_BUCKET = "my_bucket_upload"
VECTORESTORE_BUCKET ="my_vectorestore_bucket"

embedding_model = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
# groq_api_key='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'
groq_api_key ='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'
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

def download_vectore_from_gcs(user_id: str, filename: str) -> str:
    """
    Downloads the vector store folder from GCS to a temporary local directory.
    Returns the path to the downloaded vector store.
    """
    client = storage.Client()
    bucket = client.bucket(VECTORESTORE_BUCKET)  # Replace with your bucket name
    prefix = f"{user_id}/{filename}"  # Assuming your vector store is stored as a folder per user/document

    # Create a temp directory
    temp_dir = tempfile.mkdtemp()

    # List all blobs with the given prefix
    blobs = bucket.list_blobs(prefix=prefix)

    for blob in blobs:
        rel_path = os.path.relpath(blob.name, prefix)
        local_path = os.path.join(temp_dir, rel_path)
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        blob.download_to_filename(local_path)

    return temp_dir

def build_faiss_index(page_texts,embeddings):
    # Split into chunks
    docs = []
    print(len(page_texts))
    for page_no, page_text in enumerate(page_texts, start=1):
        # split into chunks directly from page text
        chunks = chunk_text(page_text)
        for i, chunk in enumerate(chunks):
            docs.append(
                Document(
                    page_content=chunk,
                    metadata={
                        "page_number": page_no,
                        "chunk_index": i
                    }
                )
            )

    vectorstore = FAISS.from_documents(docs, embeddings, distance_strategy="COSINE")
    return vectorstore

def chunk_text(text, max_words=150, overlap=20):
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk = words[i:i+max_words]
        chunks.append(" ".join(chunk))
        i += max_words - overlap  
    return chunks


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
        build_vectorstore_simple(document, file_name,VECTORESTORE_BUCKET,user["id"])

        return new_doc
    
    except Exception as e:
        logging.error("failed : {}",e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"failed to upload : {str(e)}"
        )

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

    # Delete from GCS
    delete_from_gcs(user["id"], doc_name)

    # Delete DB entry
    db.delete(document)
    db.commit()
    return {"message": f"Document '{doc_name}' deleted successfully from DB and GCS"}
    
def retrieve_best_chunks(question, vectorstore, top_k=20):
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
        context.append(f"[REF:{ref}]\n{chunk.page_content}\n[/REF]\n")

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

@router.post("/ask-question",response_model=AskQuestionResponse)
async def ask_question(db: db_dependency,filename: str = Form(...),document_type: str = Form(...),question: str = Form(...), user: dict = Depends(get_current_user)):
    file_path = download_from_gcs(user["id"], filename)
    
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
        
        vectors=save_vectore(file_path)
        best_chunks = retrieve_best_chunks(question, vectors)
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
            Answer the questions based on the provided context only.
            Please provide the most accurate response based on the context and question.
            If the answer cannot be found in the context, respond with "I don't have enough information to answer that question."
            <context>
            {context}

            <context>
            Questions:{input}
            For every response include the REF tag(s) at the END of the sentence.
            Whenever you include a reference, format it strictly as [REF:pgXcY]
            """
            )

            # vectors = build_faiss_index(content,embedding_model)
            # best_chunks = retrieve_best_chunks(question, vectors)
            
            # store_path = download_vectore_from_gcs(VECTORESTORE_BUCKET,prefix=f"{user['id']}/{filename}/")
            index, chunks, metadata = load_vectorstore_simple(VECTORESTORE_BUCKET,prefix=f"{user['id']}/{filename}/")

            # Optionally, delete temp folder after loading
            # shutil.rmtree(store_path, ignore_errors=True)
            results = similarity_search(question, index, chunks, metadata, k=22)
            print(metadata)
            context, chunk_map, ref_map= build_context(results)
            final_prompt = prompt.format(context=context, input=question)
            response = llm.invoke(final_prompt)
            result = response.content
            print(result)
            answer = replace_refs(result,chunk_map)
            print(answer)

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
    else:
        try:        
            content = extract_content(file_path)

            prompt = ChatPromptTemplate.from_template(
                """
                Summarize and give the all important details mentioned in the Query Based on provided context only  
                <context>
                {context}
                <context>
                Query:{input}
                """
            )
            vectors = build_faiss_index(content, embedding_model)

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
                
                "loan": """Document Type:
                    Document Name:
                    Date Issued:
                    Issued By:
                    Amount Borrowed:
                    Interest Rate:
                    Loan Term:
                    Repayment Schedule:
                    Prepayment Penalties:
                    Late Fees:
                    Default Terms:
                    Customer Service Contact Information:
                    Rights and Obligations:
                    Disbursement Details:
                    Grace Period:""",
                
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
            
            vectors=save_vectore(file_path)
            best_chunks = retrieve_best_chunks(english_question, vectors)
            context, chunk_map, ref_map= build_context_web(best_chunks)
            print(ref_map)
            final_prompt = prompt.format(context=context, input=english_question)
            response = llm.invoke(final_prompt)
            result = response.content
            answer = replace_refs_web(result,chunk_map)

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
                Answer the questions based on the provided context only.
                Please provide the most accurate response based on the question
                <context>
                {context}
                </context>
                Questions:{input}
                """
            )
            
            # vectors = build_faiss_index(content, embedding_model)
            # best_chunks = retrieve_best_chunks(question, vectors)
            # store_path = download_vectore_from_gcs(user["id"], filename)
            index, chunks, metadata = load_vectorstore_simple(VECTORESTORE_BUCKET,prefix=f"{user['id']}/{filename}/")
            # Optionally, delete temp folder after loading
            # shutil.rmtree(store_path, ignore_errors=True)
            results = similarity_search(question, index, chunks, metadata, k=22)
            print(metadata)
            context, chunk_map, ref_map= build_context(results)    
            final_prompt = prompt.format(context=context, input=english_question)
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
    global risk_vectors

    file_path = download_from_gcs(user["id"], filename)
    content = extract_content(file_path)

    risk_vectors[(user["id"], filename)] = build_faiss_index(content, embedding_model)
    extract(risk_vectors[(user["id"], filename)],user["id"])
    high_risk_clauses = find_high_risk_clauses(doc_type,user["id"])

    risk_results[(user["id"], filename)] = high_risk_clauses


@router.post("/high-risk-start")
async def start_high_risk(
    filename: str = Form(...),
    doc_type: str = Form(...),
    user: dict = Depends(get_current_user),
    background_tasks: BackgroundTasks = None
):
    background_tasks.add_task(run_high_risk, filename, doc_type,user)
    return {"status": "processing", "message": f"High risk analysis started for {filename}"}


@router.get("/high-risk-result/{filename}")
async def get_high_risk_result(filename: str):
    if filename not in risk_results:
        return {"status": "processing", "message": "Analysis still running..."}
    print(risk_results)
    return {
        "status": "done",
        "high_risk_clauses": risk_results[filename]
    }

@router.get("/get-reference/{ref}")
async def get_reference(ref: str, filename: str, user: dict = Depends(get_current_user)):

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