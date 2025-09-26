from langchain_community.vectorstores import FAISS
from langchain.docstore.document import Document
from langchain_huggingface import HuggingFaceEmbeddings
from groq import Groq
import re
import os

client = Groq(api_key="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")

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

def extract(vectorstore):

    all_chunks = list(vectorstore.docstore._dict.values())

    BATCH_SIZE = 2
    total_chunks = len(all_chunks)

    print(f"Total chunks to process: {total_chunks}")
    print(f"Processing in batches of {BATCH_SIZE}")

    for batch_start in range(0, total_chunks, BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, total_chunks)
        current_batch = all_chunks[batch_start:batch_end]
        
        print(f"\nProcessing batch {batch_start//BATCH_SIZE + 1}: chunks {batch_start + 1}-{batch_end}")
        
        context = ""
        for doc in current_batch:
            content = doc.page_content
            meta = doc.metadata
            # Build a compact metadata string
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

        with open("./uploads/clauses.json","a",encoding="utf-8") as f:
            f.write(response.choices[0].message.content)

    
    with open("./uploads/clauses.json", "r", encoding="utf-8") as f:
        data = f.read()

    cleaned_data = data.replace("][",",")
    cleaned_data = re.sub(r"\{[^{}]*\{", "{", cleaned_data)
    cleaned_data = re.sub(r",+", ",", cleaned_data)

    if os.path.exists("./uploads/clauses.json"):
        os.remove("./uploads/clauses.json")

    with open("./uploads/clean.json","w", encoding="utf-8") as f:
        f.write(cleaned_data)
    