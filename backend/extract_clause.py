from langchain_community.vectorstores import FAISS
from langchain.docstore.document import Document
from langchain_huggingface import HuggingFaceEmbeddings
from groq import Groq
import re
import os
from google.cloud import storage
import tempfile
import random

API_KEYS = [
    "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",
    "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",
]

api_key = random.choice(API_KEYS)

client = Groq(api_key=api_key)

embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

SYSTEM_INSTRUCTIONS = """You are an expert legal clause extractor specializing in agreements.

Extract only legal clauses from the provided text, focusing on:
- Penalties 
- Obligations 
- Exclusions 
- Fees 
- Payment 
- Indemnity 
- Terminal 
- Lock-in period 
- Renewal   
- Sole discretion 

IMPORTANT GROUPING RULES:
1. Group related sentences that form one complete legal provision into a SINGLE clause
2. Do NOT split a complete legal concept into multiple separate clauses
3. Headers/titles should be combined with their corresponding explanatory text
4. Sequential sentences about the same subject matter should be merged
5. Only merge sentences that are describing the SAME legal provision or requirement
6. Combine all related fees, charges, and costs that appear together as a single comprehensive fee structure
7. LISTS When multiple items form a complete list or schedule (fees, penalties, conditions, benefits), group them as ONE clause

OUTPUT FORMAT RULES:
- Always return valid JSON
- Do NOT include categories as keys
- Do not repeat the same clause again. 
- Ensure all JSON is properly closed
- Each object must have exactly:
  {
    "clause": "<full clause text here>",
    "REF": "<pgXckY>"
  }
- If no clauses are found, return []
- Strictly only return a flat array of objects
"""
USER_TEMPLATE = """
Analyze this document text and extract all legal and important clauses: text : {context}

Return results strictly in JSON format as a flat list of objects:
[
  {{
    "clause": "...",
    "REF": "PgXckY"
  }}
]
"""

UPLOAD_BUCKET = "my_bucket_upload"   
TMP_DIR = "/tmp"

def save_to_gcs(local_path: str, gcs_path: str):
    """Upload a local file to GCS"""
    storage_client = storage.Client()
    bucket = storage_client.bucket(UPLOAD_BUCKET)
    blob = bucket.blob(gcs_path)
    blob.upload_from_filename(local_path)
    print(f"Uploaded {local_path} -> gs://{UPLOAD_BUCKET}/{gcs_path}")

def extract(vectorstore, user_id: int):
    all_chunks = list(vectorstore.docstore._dict.values())

    BATCH_SIZE = 2
    total_chunks = len(all_chunks)

    print(f"Total chunks to process: {total_chunks}")
    print(f"Processing in batches of {BATCH_SIZE}")

    tmp_clauses_path = os.path.join(TMP_DIR, "clauses.json")

    # Start fresh each time
    if os.path.exists(tmp_clauses_path):
        os.remove(tmp_clauses_path)

    for batch_start in range(0, total_chunks, BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, total_chunks)
        current_batch = all_chunks[batch_start:batch_end]

        print(f"\nProcessing batch {batch_start//BATCH_SIZE + 1}: chunks {batch_start + 1}-{batch_end}")

        context = ""
        for doc in current_batch:
            content = doc.page_content
            meta = doc.metadata
            meta_str = f"pg{meta.get('page_number', 0)}ck{meta.get('chunk_index', 0)}"
            context += f"Content: {content}\n[REF]: {meta_str} [REF]\n"

        print(f"Context length for this batch: {len(context)} characters")

        prompt = USER_TEMPLATE.format(context=context)

        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                {"role": "user", "content": prompt}
            ],
            max_tokens=6000,
            temperature=0.1
        )

        # Append results to tmp file
        with open(tmp_clauses_path, "a", encoding="utf-8") as f:
            f.write(response.choices[0].message.content)

    # Post-process
    with open(tmp_clauses_path, "r", encoding="utf-8") as f:
        data = f.read()

    cleaned_data = data.replace("][", ",")
    cleaned_data = re.sub(r"\{[^{}]*\{", "{", cleaned_data)
    cleaned_data = re.sub(r",+", ",", cleaned_data)

    tmp_clean_path = os.path.join(TMP_DIR, "clean.json")
    with open(tmp_clean_path, "w", encoding="utf-8") as f:
        f.write(cleaned_data)

    # Save final clean.json into GCS (per-user folder)
    save_to_gcs(tmp_clean_path, f"{user_id}/clean.json")

    print(f"Final cleaned JSON saved to gs://{UPLOAD_BUCKET}/{user_id}/clean.json")

    return f"gs://{UPLOAD_BUCKET}/{user_id}/clean.json"
    