from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from groq import Groq
import re
import json
from collections import defaultdict
from google.cloud import storage
import os

UPLOAD_BUCKET = "my_upload_bucket"

embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
client = Groq(api_key="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")

def load_url_mapping_gcs():
    """Load URL mapping from GCS bucket"""
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(UPLOAD_BUCKET)
        blob = bucket.blob("url_mapping.json")
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as tmp_file:
            blob.download_to_filename(tmp_file.name)
            tmp_file_path = tmp_file.name
        with open(tmp_file_path, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Could not load URL mapping from GCS: {e}")
        return {}
    
def load_faiss_index_from_gcs():
    storage_client = storage.Client()
    bucket = storage_client.bucket(UPLOAD_BUCKET)
    
    temp_dir = "/tmp"
    
    blobs = bucket.list_blobs(prefix="faiss_index_directory/")
    for blob in blobs:
        relative_path = blob.name.replace("faiss_index_directory/", "")
        local_path = os.path.join(temp_dir, relative_path)
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        blob.download_to_filename(local_path)
    
    vectorstore = FAISS.load_local(temp_dir, embeddings, allow_dangerous_deserialization=True)
    return vectorstore

def group_chunks_by_url(chunks):
    """Group chunks by their primary URL to avoid fragmentation"""
    url_groups = defaultdict(list)
    
    for chunk in chunks:
        content = chunk[0]
        url = chunk[1]
        
        # Skip very short or repetitive content
        if len(content.strip()) < 50:
            continue
            
        url_groups[url].append(content)
    
    print(f"Grouped content into {len(url_groups)} URL groups")
    for url, contents in url_groups.items():
        print(f"  {url}: {len(contents)} chunks")
    
    return url_groups

def create_content_batches(url_groups, max_length=3000):
    """Create batches ensuring content doesn't exceed token limits"""
    batches = []
    
    for url, contents in url_groups.items():
        # Combine all content for this URL
        combined_content = " ".join(contents)
        
        # If content is too long, split it intelligently
        if len(combined_content) > max_length:
            # Split by sentences to maintain coherence
            sentences = re.split(r'(?<=[.!?])\s+', combined_content)
            current_batch = ""
            
            for sentence in sentences:
                if len(current_batch + sentence) > max_length:
                    if current_batch:
                        batches.append((current_batch.strip(), url))
                        current_batch = sentence
                    else:
                        # Single sentence is too long, truncate it
                        batches.append((sentence[:max_length].strip(), url))
                else:
                    current_batch += " " + sentence
            
            if current_batch.strip():
                batches.append((current_batch.strip(), url))
        else:
            batches.append((combined_content.strip(), url))
    
    return batches

def summarize_content_batch(content, url, batch_num, total_batches):
    """Summarize a single content batch with its URL"""
    prompt = f"""
    Summarize the following content into a clear, coherent paragraph of 4-5 sentences. Focus on the main topics, key points, and overall purpose of the content. Ignore any formatting issues or garbled text.
    
    Content to summarize:
    {content}
    
    Provide only a clean, well-written summary without mentioning formatting issues or technical problems.
    """
    
    try:
        print(f"Summarizing batch {batch_num}/{total_batches}...")
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=400,
        )
        summary = response.choices[0].message.content.strip()
        return f"{summary} {url}"
    except Exception as e:
        print(f"Error summarizing batch {batch_num}: {e}")
        return f"Unable to process content from this source. {url}"

def create_final_summary(batch_summaries):
    """Create final organized summary"""
    # Remove duplicates and clean up
    unique_summaries = []
    seen_content = set()
    
    for summary in batch_summaries:
        # Extract content and URL
        url_match = re.search(r'https?://[^\s]+', summary)
        if url_match:
            url = url_match.group()
            content = summary.replace(url, '').strip()
        else:
            url = ""
            content = summary.strip()
        
        # Skip if we've seen similar content
        content_key = content[:100].lower()  # Use first 100 chars as key
        if content_key not in seen_content and len(content) > 50:
            seen_content.add(content_key)
            unique_summaries.append((content, url))
    
    print(f"Final summary contains {len(unique_summaries)} unique summaries")
    
    # Format final output
    final_output = []
    for i, (content, url) in enumerate(unique_summaries, 1):
        if url:
            final_output.append(f"{content} {url}")
        else:
            final_output.append(content)
        print(f"Summary {i}: {content[:100]}... -> {url}")
    
    return "\n\n".join(final_output)

def summary(vectorstore):
    """Main summarization function"""
    print("Loading FAISS index...")
    
    # Try to load improved index first, then fall back to original
    # try:
    #     load_faiss_index_from_gcs()
    #     print("Loaded improved FAISS index")
    # except:
    #     try:
    #         vectorstore = FAISS.load_local(
    #             "faiss_index_directory",
    #             embeddings,
    #             allow_dangerous_deserialization=True
    #         )
    #         print("Loaded original FAISS index")
    #     except Exception as e:
    #         print(f"Error loading FAISS index: {e}")
    #         return None
    
    # Load URL mapping
    # url_mapping = load_url_mapping_gcs()
    
    # Get all documents
    all_docs = vectorstore.docstore._dict.values()
    chunks = []
    
    for doc in all_docs:
        # Get primary URL from metadata, with fallback logic
        primary_url = doc.metadata.get('primary_url')
        if not primary_url or primary_url == "No URL available":
            # Try to get from urls list
            urls = doc.metadata.get('urls', [])
            primary_url = urls[0] if urls else "No URL available"
        
        chunks.append([doc.page_content, primary_url])
    
    print(f"Processing {len(chunks)} chunks...")
    
    # Debug: Show URL distribution
    url_counts = {}
    for chunk in chunks:
        url = chunk[1]
        url_counts[url] = url_counts.get(url, 0) + 1
    
    print("URL distribution:")
    for url, count in url_counts.items():
        print(f"  {url}: {count} chunks")
    
    # Group chunks by URL
    url_groups = group_chunks_by_url(chunks)
    
    # Create content batches
    content_batches = create_content_batches(url_groups)
    print(f"Created {len(content_batches)} content batches")
    
    # Summarize each batch
    batch_summaries = []
    for i, (content, url) in enumerate(content_batches):
        summary = summarize_content_batch(content, url, i+1, len(content_batches))
        batch_summaries.append(summary)
    
    # Create final summary
    final_summary = create_final_summary(batch_summaries)
    
    return final_summary