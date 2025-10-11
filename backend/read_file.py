import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io
import zipfile
from langchain_community.document_loaders import Docx2txtLoader, TextLoader
from langchain.schema import Document
import concurrent.futures
import time

def process_pdf_page(page_num, page):
    """Processes a single PDF page: extracts text and OCRs images."""
    page_text = page.get_text("text").strip()
    images = page.get_images(full=True)

    # Case 1: Text + Images (Hybrid)
    if page_text and images:
        ocr_texts = []
        for img_index, img in enumerate(images):
            xref = img[0]
            base_image = page.parent.extract_image(xref)
            image_bytes = base_image["image"]
            try:
                image = Image.open(io.BytesIO(image_bytes))
                ocr_text = pytesseract.image_to_string(image)
                if ocr_text.strip():
                    ocr_texts.append(ocr_text)
            except Exception as e:
                print(f"Skipping image {img_index}: {e}")

        merged = page_text + "\n" + "\n".join(ocr_texts)
        return page_num, merged.strip()

    # Case 2: Text only
    elif page_text:
        return page_num, page_text

    # Case 3: Image only
    else:
        pix = page.get_pixmap(dpi=300)
        image = Image.open(io.BytesIO(pix.tobytes("png")))
        text = pytesseract.image_to_string(image)
        return page_num, text.strip()

def extract_content(file_path):
    if file_path.endswith("pdf"):
        doc = fitz.open(file_path)
        num_pages = len(doc)

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            # Submit tasks with page number
            futures = [executor.submit(process_pdf_page, i, doc.load_page(i)) for i in range(num_pages)]

            # Collect results
            results = [f.result() for f in futures]

        # Sort results by page number to preserve page order
        results_sorted = [text for page_num, text in sorted(results, key=lambda x: x[0])]
        return results_sorted

    elif file_path.endswith("docx"):
        loader = Docx2txtLoader(file_path)
        text_docs = loader.load()

        ocr_docs = []
        with zipfile.ZipFile(file_path, 'r') as z:
            for name in z.namelist():
                if name.startswith("word/media/") and not name.endswith("/"):
                    image_data = z.read(name)
                    try:
                        image = Image.open(io.BytesIO(image_data))
                        ocr_text = pytesseract.image_to_string(image).strip()
                        if ocr_text:
                            ocr_docs.append(Document(page_content=ocr_text))
                    except Exception:
                        continue

        return text_docs + ocr_docs

    elif file_path.endswith("txt"):
        loader = TextLoader(file_path)
        docs = loader.load()
        return [docs[0].page_content]

    else:
        raise ValueError("Unsupported file type for reading content.")