import re
import spacy
from groq import Groq
from datetime import date
import os

groq_api_key = os.environ.get('GROQ_API_KEY4')
client = Groq(api_key= groq_api_key)

prompt_template = """ Extract important dates from the given sentences including: {dates} if specified.

For recurring payment patterns (like "every month"), calculate the next 6 occurrences starting from {today_date}.

generate dates for next six months only.

CRITICAL: Follow this exact output format:
- Each date must be in DD-MM-YYYY format
- Each line must follow: DD-MM-YYYY - description
- No numbering, no bullet points, no explanations
- No additional text or assumptions

Example output:
DD-MM-YYYY - Payment due date
DD-MM-YYYY - Statement date
DD-MM-YYYY - Grace period ends

Sentences: {sentences}
"""

def sentences_with_date_entity(page_texts):
    text = re.sub(r"[●•▪]", "", page_texts)
    text = text.replace("\u200b","")
    text = text.lower()
    print(text)

    sents = re.split(r'[\n\-]+', text)
    sents= [c.strip() for c in sents if c.strip()]

    nlp=spacy.load("en_core_web_trf")

    # 🔹 Step 2: Run spaCy NER and keep only clauses with DATE entities
    sentences_with_dates = []
    for sent in sents:
        doc = nlp(sent)
        dates = [ent.text for ent in doc.ents if ent.label_ == "DATE"]
        if dates:
            sentences_with_dates.append(sent)

    return sentences_with_dates

def call_lm(sents,doc_type):

    today = date.today()
    formatted_date = today.strftime("%d-%b-%Y")

    if doc_type == "credit_card_terms":
        dates = "due dates, renewal dates, grace period end dates, statement dates, billing cycle dates"

    elif doc_type == "loan":
        dates = "disbursement dates, first EMI dates, installment due dates, maturity dates, prepayment/foreclosure dates, default trigger dates, interest reset dates"

    elif doc_type == "tender":
        dates = "tender issue dates, bid submission deadlines, pre-bid meeting dates, bid opening dates, contract award dates, completion/delivery dates, validity period end dates, renewal/extension dates"

    elif doc_type == "policy":
        dates = "policy start/commencement dates, policy expiry/renewal dates, premium due dates, grace period end dates, free-look period end dates, claim filing deadlines, maturity dates"

    else:
        dates = "start dates, end dates, due dates, renewal dates, expiry dates"
    
    prompt = prompt_template.format(dates=dates,sentences=sents,today_date=formatted_date)

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages = [
            {'role':'user','content':prompt}
        ],
        max_tokens = 512,
        temperature = 0.1
    )

    print(response.choices[0].message.content)
    return response.choices[0].message.content