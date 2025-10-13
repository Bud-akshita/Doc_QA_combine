import json
import re
from typing import Dict, List, Tuple, Optional
from langchain_huggingface import HuggingFaceEmbeddings
import os

embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2",model_kwargs={"use_auth_token": os.environ.get("HF_TOKEN")})

import re
from typing import Tuple

from google.cloud import storage
import tempfile

UPLOAD_BUCKET = "my_bucket_upload"

def assess_clause_risk(clause_text: str, doc_type: str) -> Tuple[str, str]:
    """
    Assess risk level of a legal clause based on its text and document type.
    Returns: (risk_level, reasoning)
    """

    text_lower = clause_text.lower()

    core_high_risk = [
        r'penalty|fine|charge.*breach|default.*fee|forfeit|confiscat',
        r'sole discretion|absolute discretion|may.*without.*notice|reserve.*right.*modify',
        r'terminate.*immediately|cancel.*without.*cause|foreclosure|lapse.*policy',
        r'exclude|not.*cover|limitation.*liability|disclaim|void.*policy',
        r'additional.*premium|extra.*charge|interest.*compound|outstanding.*amount',
        r'legal.*action|court.*proceeding|indemnify|liable.*damage'
    ]

    core_medium_risk = [
        r'subject.*to|provided.*that|condition.*apply|requirement.*fulfill',
        r'grace.*period|revival.*period|due.*date|within.*day',
        r'underwriting|approval.*require|satisf.*corporation|document.*submit',
        r'premium.*payable|installment|repayment|maturity.*benefit',
        r'assignment|nomination|transfer.*right|beneficiary'
    ]

    core_low_risk = [
        r'means|defined.*as|refers.*to|shall.*be|definition',
        r'policy.*document|schedule|certificate|date.*of.*commence',
        r'life.*assured|policyholder|proposer|corporation.*mean'
    ]

    doc_specific = {
        "loan": {
            "high": [r'collateral|pledge|mortgage|guarantor|hypothecat',
                     r'default.*interest|penal.*rate',
                     r'foreclosure.*without.*notice'],
            "medium": [r'emis|repayment.*schedule|prepayment|rescheduling',
                       r'security.*cover|valuation.*asset'],
            "low": [r'loan.*agreement|borrower|lender']
        },
        "tender": {
            "high": [r'blacklist|forfeit.*bid|disqualif',
                     r'non[- ]compliance.*penalty',
                     r'performance.*guarantee.*invoke'],
            "medium": [r'bid.*validity|submission.*deadline|clarification',
                       r'earnest.*money.*deposit|emd'],
            "low": [r'tender.*document|corrigendum|bidder']
        },
        "insurance": {
            "high": [r'non[- ]disclosure|misrepresentation.*void',
                     r'claim.*repudiat|policy.*void',
                     r'exclusion.*death|suicide|war|terrorism'],
            "medium": [r'waiting.*period|free[- ]look.*period',
                       r'premium.*due|revival.*benefit'],
            "low": [r'policyholder|insured|nominee']
        },
        "credit_card_terms": {
            "high": [r'overlimit.*fee|late.*payment.*charge',
                     r'bank.*terminate.*without.*notice',
                     r'interest.*per.*month|compounded'],
            "medium": [r'annual.*fee|renewal.*charge',
                       r'grace.*period|billing.*cycle',
                       r'cash.*advance.*fee'],
            "low": [r'cardholder|credit.*limit|statement.*date']
        }
    }

    mitigation_patterns = [
    r'nil.*charge', 
    r'no.*fee', 
    r'without.*charge', 
    r'free.*of.*cost'
    ]

    # ---------------- Merge patterns ----------------
    high_risk_patterns = core_high_risk + doc_specific.get(doc_type, {}).get("high", [])
    medium_risk_patterns = core_medium_risk + doc_specific.get(doc_type, {}).get("medium", [])
    low_risk_patterns = core_low_risk + doc_specific.get(doc_type, {}).get("low", [])

    # ---------------- Scoring ----------------
    risk_score = 0
    risk_reasons = []

    for pattern in high_risk_patterns:
        if re.search(pattern, text_lower):
            risk_score += 3
            risk_reasons.append(f"HIGH risk: matched '{pattern}'")

    for pattern in medium_risk_patterns:
        if re.search(pattern, text_lower):
            risk_score += 2
            risk_reasons.append(f"MEDIUM risk: matched '{pattern}'")

    for pattern in low_risk_patterns:
        if re.search(pattern, text_lower):
            risk_score += 1
            risk_reasons.append(f"LOW risk: matched '{pattern}'")

    for pattern in mitigation_patterns:
        if re.search(pattern, text_lower):
            risk_score -= 2  

    if risk_score >= 7:
        risk_level = "HIGH"
    elif risk_score >= 3:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    reasoning = "; ".join(risk_reasons[:3]) if risk_reasons else "No risk indicators found"

    return risk_level, reasoning

def process_clauses_file(json_data: List[Dict],doc_type) -> List[Dict]:
    """
    Process the clause data and add risk assessments
    """
    processed_clauses = []
    
    for item in json_data:
        clause_text = item.get('clause', '')
        ref = item.get('REF', '')
        
        risk_level, reasoning = assess_clause_risk(clause_text,doc_type)
        
        processed_clause = {
            "clause": clause_text,
            "REF": ref,
            "risk_level": risk_level,
            "risk_reasoning": reasoning
        }
            
        processed_clauses.append(processed_clause)
    
    return processed_clauses

def categorize_by_risk(clauses: List[Dict]) -> Dict[str, List[Dict]]:
    """Categorize clauses by risk level"""
    risk_categories = {"HIGH": [], "MEDIUM": [], "LOW": []}
    
    for clause in clauses:
        risk_level = clause.get('risk_level', 'LOW')
        risk_categories[risk_level].append(clause)
    
    return risk_categories

def get_reference_chunk(vectorstore,ref: str) -> Optional[Dict]:
    """
    Get reference chunk information from FAISS index
    """
    
    pattern = r"pg(\d+)ck(\d+)"
    match = re.match(pattern, str(ref))
    
    if not match:
        return None
    
    try:
        page_no, chunk_idx = match.groups()
        metadata = {
            "page_number": int(page_no),
            "chunk_index": int(chunk_idx)
        }
        
        for doc in vectorstore.docstore._dict.values():
            if doc.metadata == metadata:
                return {
                    "page_number": metadata['page_number'],
                    "chunk_index": metadata['chunk_index'],
                    "content": doc.page_content,
                    "reference": ref
                }
        
        return None
        
    except Exception as e:
        print(f"Error retrieving reference {ref}: {str(e)}")
        return None

def find_high_risk_clauses(doc_type,user_id,filename) -> List[Dict]:
    """
    Find and return all high-risk clauses from the processed file stored in GCS
    """
    try:
        # Create GCS client
        storage_client = storage.Client()
        bucket = storage_client.bucket(UPLOAD_BUCKET)
        blob = bucket.blob(f"{user_id}/{filename}/clean.json")   # clean.json at bucket root (adjust path if nested)

        # Download to a temporary file
        with tempfile.NamedTemporaryFile(mode="w+b", delete=False) as tmp_file:
            blob.download_to_filename(tmp_file.name)
            tmp_file_path = tmp_file.name

        # Load JSON from downloaded file
        with open(tmp_file_path, "r", encoding="utf-8") as f:
            clauses = json.load(f)

        # Process and categorize
        processed = process_clauses_file(clauses, doc_type)
        categories = categorize_by_risk(processed)

        return categories["HIGH"]

    except FileNotFoundError:
        print("clean.json file not found in bucket")
        return []
    except json.JSONDecodeError:
        print("Error parsing clean.json file")
        return []
    except Exception as e:
        print(f"Error finding high-risk clauses: {str(e)}")
        return []