import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io
import zipfile
from langchain_community.document_loaders import Docx2txtLoader, TextLoader
from langchain.schema import Document

def extract_content(file_path):
    all_docs = []

    if file_path.endswith("pdf"):
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
                print("using ocr on full page")
                page = doc[page_num]
                pix = page.get_pixmap(dpi=200)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                text = pytesseract.image_to_string(img)
                page_texts.append(text.strip())
            return page_texts 
        return all_docs

    elif file_path.endswith('docx'):
        loader = Docx2txtLoader(file_path)
        text_docs = loader.load()  # list[Document] from PDF text
        
        ocr_docs = []  # list to store OCR-based Document objects
        with zipfile.ZipFile(file_path, 'r') as z:
            # Images live under word/media/
            for name in z.namelist():
                if name.startswith("word/media/") and not name.endswith("/"):
                    image_data = z.read(name)
                    try:
                        image = Image.open(io.BytesIO(image_data))
                    except Exception as e:
                        continue  # skip unreadable
                    ocr_text = pytesseract.image_to_string(image).strip()
                    
                    if ocr_text.strip():  # only add if OCR found text
                        ocr_docs.append(Document(page_content=ocr_text))
                        
        all_docs = text_docs + ocr_docs
        return all_docs  
        
    elif file_path.endswith("txt"):
        loader = TextLoader(file_path)
        docs = loader.load()
        return [docs[0].page_content]
    else:
        raise ValueError("Unsupported file type for reading content.")