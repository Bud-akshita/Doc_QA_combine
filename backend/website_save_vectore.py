from langchain_community.vectorstores import FAISS
from langchain.docstore.document import Document
from langchain_huggingface import HuggingFaceEmbeddings
import re
from langchain.text_splitter import RecursiveCharacterTextSplitter
import fitz
import json
from google.cloud import storage
import tempfile
import shutil
import os
import pickle
import io

# Embedding model wrapper for LangChain
embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2",model_kwargs={"use_auth_token": os.environ.get["HF_TOKEN"]})

UPLOAD_BUCKET = "my_bucket_upload"

def clean_text(text):
    """Clean and normalize text content"""
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text)
    # Remove garbled characters patterns
    text = re.sub(r'[^\w\s\.\,\!\?\;\:\-\(\)\[\]\/\@\#\$\%\&\*\+\=\<\>\|\{\}\~\`\'\"]', '', text)
    # Remove repeated patterns
    text = re.sub(r'(.{10,}?)\1{2,}', r'\1', text)
    return text.strip()

def extract_urls_and_clean_text(text):
    """Extract all URLs and return cleaned text with URL list"""
    url_pattern = r'https?://[^\s]+'
    urls = list(set(re.findall(url_pattern, text)))  # Remove duplicates
    # Remove URLs from text
    cleaned_text = re.sub(url_pattern, '', text)
    cleaned_text = clean_text(cleaned_text)
    return cleaned_text, urls

def build_faiss_index(page_texts, chunk_size=800, chunk_overlap=100):
    
    # Initialize text splitter with larger chunks
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
    )
    
    docs = []
    url_mapping = {}  
    last_found_url = "No URL available"  
    
    print(f"Processing {len(page_texts)} pages...")
    
    # Sort pages by page number to ensure proper order
    sorted_pages = sorted(page_texts.items(), key=lambda x: x[0])
    
    for page_no, page_text in sorted_pages:
        # Clean and extract URLs from the entire page first
        cleaned_page_text, page_urls = extract_urls_and_clean_text(page_text)
        
        # Implement URL carry-forward logic
        if page_urls:
            # Found URLs in current page - use them and update last_found_url
            current_url = page_urls[0]
            last_found_url = current_url
            url_mapping[page_no] = page_urls
        else:
            # No URLs found - use the last found URL
            current_url = last_found_url
            url_mapping[page_no] = [last_found_url] if last_found_url != "No URL available" else []
        
        print(f"Page {page_no}: Found {len(page_urls)} URLs, using URL: {current_url}, cleaned text length: {len(cleaned_page_text)}")
        
        # Skip if page is too short after cleaning
        if len(cleaned_page_text.strip()) < 100:
            print(f"Skipping page {page_no} - too short after cleaning")
            continue
            
        # Split cleaned text into chunks
        chunks = text_splitter.split_text(cleaned_page_text)
        print(f"Page {page_no}: Created {len(chunks)} chunks")
        
        for chunk_idx, chunk in enumerate(chunks):
            # Skip very short chunks
            if len(chunk.strip()) < 50:
                continue
                
            # Create metadata with assigned URL (either found or carried forward)
            metadata = {
                "page_number": page_no,
                "chunk_index": chunk_idx,
                "urls": [current_url],
                "primary_url": current_url,
                "url_source": "found" if page_urls else "carried_forward"
            }
            
            # Create Document object
            doc = Document(
                page_content=chunk.strip(),
                metadata=metadata
            )
            
            docs.append(doc)
    
    print(f"Created {len(docs)} total document chunks")
    print("Final URL mapping with carry-forward logic:")
    for page_no, urls in sorted(url_mapping.items()):
        source = "found" if any(url in str(page_texts.get(page_no, "")) for url in urls) else "carried forward"
        print(f"  Page {page_no}: {urls} ({source})")
    
    # Build vector store
    vectorstore = FAISS.from_documents(docs, embeddings)

    # Save URL mapping locally first
    with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".json") as tmp_file:
        json.dump(url_mapping, tmp_file, indent=2)
        tmp_file.flush()
        tmp_file_path = tmp_file.name

    # Upload URL mapping.json to GCS
    storage_client = storage.Client()
    bucket = storage_client.bucket(UPLOAD_BUCKET)
    blob = bucket.blob("url_mapping.json")
    blob.upload_from_filename(tmp_file_path)

    return vectorstore, url_mapping

def save_vectore(pdf):
    print("Building improved FAISS index...")
    
    # Read PDF
    doc = fitz.open(pdf)
    page_texts = {page_num + 1: doc[page_num].get_text().strip() for page_num in range(len(doc))}
    
    # Build index
    vectorstore, url_mapping = build_faiss_index(page_texts, chunk_size=800, chunk_overlap=100)
    index_buffers = {}

    # Save FAISS index itself
    buf_index = io.BytesIO()
    faiss_index = vectorstore.index
    pickle.dump(faiss_index, buf_index)
    buf_index.seek(0)
    index_buffers["faiss.index"] = buf_index

    # Save docstore (documents with metadata)
    buf_docstore = io.BytesIO()
    pickle.dump(vectorstore.docstore, buf_docstore)
    buf_docstore.seek(0)
    index_buffers["docstore.pkl"] = buf_docstore

    # Save mapping from vector IDs → docstore IDs
    buf_mapping = io.BytesIO()
    pickle.dump(vectorstore.index_to_docstore_id, buf_mapping)
    buf_mapping.seek(0)
    index_buffers["index_to_docstore_id.pkl"] = buf_mapping

    # Upload to GCS
    storage_client = storage.Client()
    bucket = storage_client.bucket(UPLOAD_BUCKET)  # you had bucket_name undefined
    for filename, buf in index_buffers.items():
        blob = bucket.blob(f"faiss_index/{filename}")
        blob.upload_from_file(buf, rewind=True)

    print("FAISS index uploaded successfully to GCS!")
    print(f"URL mapping: {url_mapping}")

    return vectorstore