import re
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import simpleSplit

from transformers import MarianTokenizer, MarianMTModel

# Load the translation model once
model_name = "Helsinki-NLP/opus-mt-en-hi"
tokenizer = MarianTokenizer.from_pretrained(model_name)
model = MarianMTModel.from_pretrained(model_name)


def split_into_sentences(text: str):
    """Split text into sentences (handles ., ?, !)."""
    sentences = re.split(r'(?<=[\.\?\!])\s+', text)
    return [s.strip() for s in sentences if s.strip()]


def chunk_sentences_by_tokens(sentences, tokenizer, max_tokens: int = 400):
    """Accumulate sentences into chunks <= max_tokens."""
    chunks = []
    current, current_len = "", 0

    for sent in sentences:
        tok_len = len(tokenizer(sent, add_special_tokens=False).input_ids)

        if current_len + tok_len <= max_tokens:
            current = (current + " " + sent).strip()
            current_len += tok_len
        else:
            if current:
                chunks.append(current)
            # If one sentence itself is too long, split by raw tokens
            if tok_len > max_tokens:
                tokens = tokenizer(sent, add_special_tokens=False).input_ids
                for i in range(0, len(tokens), max_tokens):
                    piece = tokens[i:i + max_tokens]
                    chunks.append(tokenizer.decode(piece, skip_special_tokens=True))
                current, current_len = "", 0
            else:
                current, current_len = sent, tok_len

    if current:
        chunks.append(current)

    return chunks


def translate_to_hindi(text: str) -> str:
    """Translate text into Hindi safely with sentence + token chunking."""
    sentences = split_into_sentences(text)
    chunks = chunk_sentences_by_tokens(sentences, tokenizer, max_tokens=400)
    translations = []

    for part in chunks:
        print("EN chunk:", part[:120], "...")
        inputs = tokenizer(part, return_tensors="pt", padding=True, truncation=True)
        translated_tokens = model.generate(**inputs, max_length=512)
        hindi_text = tokenizer.decode(translated_tokens[0], skip_special_tokens=True)
        print("HI translation:", hindi_text[:120], "...")
        translations.append(hindi_text.strip())

    return "\n\n".join(translations)


def save_pdf(text, output_filename="output.pdf"):
    """Save Hindi text to PDF with proper font + wrapping."""
    pdfmetrics.registerFont(TTFont("NotoSansDevanagari", "NotoSansDevanagari.ttf"))
    c = canvas.Canvas(output_filename, pagesize=A4)

    width, height = A4
    margin = 50
    line_height = 20
    max_width = width - 2 * margin

    c.setFont("NotoSansDevanagari", 12)
    y = height - margin

    paragraphs = text.split("\n\n")
    for para in paragraphs:
        lines = simpleSplit(para, "NotoSansDevanagari", 12, max_width)
        for line in lines:
            c.drawString(margin, y, line)
            y -= line_height
            if y < margin:
                c.showPage()
                c.setFont("NotoSansDevanagari", 12)
                y = height - margin
        y -= line_height  # add spacing between paragraphs

    c.save()
    print(f"✅ PDF saved as {output_filename}")
