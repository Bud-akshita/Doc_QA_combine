from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import FileResponse
from urllib.parse import urljoin, urlparse
from collections import deque
from bs4 import BeautifulSoup
from fpdf import FPDF
import os
import re
import concurrent.futures
import requests

from database import db_dependency
from pydantic import BaseModel, Field
from auth import get_current_user
from models import Documents
from io import BytesIO

from google.cloud import storage

bucket_name = 'my_bucket_upload'

router = APIRouter(
    prefix="/website",
    tags=["website"]
)

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

def is_file_url(url):
    """
    Check if URL points to a file (image, document, etc.)
    """
    parsed_url = urlparse(url)
    path = parsed_url.path.lower()
    
    # Common file extensions to exclude
    file_extensions = {
        '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.svg', '.ico',
        '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
        '.zip', '.rar', '.7z', '.tar', '.gz',
        '.mp4', '.mp3', '.avi', '.mov', '.wmv', '.flv',
        '.css', '.js', '.xml', '.json', '.txt'
    }
    
    # Check if path ends with any file extension
    return any(path.endswith(ext) for ext in file_extensions)

def get_sitemap_urls_recursive(url, max_urls=25):
    """
    Recursively get URLs from sitemap, handling sitemap indexes
    Filters out image files and other non-HTML content
    """
    urls = []
    
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "xml")
        
        # Check if this is a sitemap index (contains <sitemap> tags)
        sitemap_tags = soup.find_all("sitemap")
        if sitemap_tags:
            for sitemap in sitemap_tags:
                if len(urls) >= max_urls:
                    break
                loc = sitemap.find("loc")
                if loc and loc.text:
                    sitemap_url = loc.text
                    # Recursively process nested sitemap
                    nested_urls = get_sitemap_urls_recursive(sitemap_url, max_urls - len(urls))
                    urls.extend(nested_urls)
        else:
            # This is a regular sitemap with URLs
            url_tags = soup.find_all("url") or soup.find_all("loc")
            for url_tag in url_tags:
                if len(urls) >= max_urls:
                    break
                loc = url_tag.find("loc") if url_tag.name == "url" else url_tag
                if loc and loc.text:
                    url_text = loc.text.strip()
                    # Filter out image files and other non-HTML content
                    if not is_file_url(url_text):
                        urls.append(url_text)
    
    except Exception:
        # If sitemap fetch fails, return empty list
        pass
    
    return urls[:max_urls]

def extract_text_with_bs(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        tag.extract()
    return soup.get_text(separator=" ", strip=True)

def crawl_site(base_url, max_pages=20): 
    visited = set() 
    queue = deque([base_url]) 
    domain = urlparse(base_url).netloc 
    found_urls = [] 

    while queue and len(found_urls) < max_pages: 
        url = queue.popleft() 
        if url in visited: 
            continue 
        visited.add(url) 

        try: 
            resp = requests.get(url, headers=headers, timeout=15) 
            if resp.status_code != 200: 
                continue 
        except Exception: 
            continue 

        found_urls.append(url) 
        soup = BeautifulSoup(resp.text, "html.parser") 
        for link in soup.find_all("a", href=True): 
            new_url = urljoin(url, link["href"]) 
            if (urlparse(new_url).netloc == domain and 
                new_url not in visited and 
                not is_file_url(new_url)):  # Use the improved filtering function
                queue.append(new_url) 
    return found_urls

def fetch_page_with_requests(url):
    """Fetch page content using requests"""
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        if resp.status_code == 200:
            # Check if content is HTML before parsing
            content_type = resp.headers.get('content-type', '').lower()
            if 'text/html' in content_type:
                text = extract_text_with_bs(resp.text)
                return url, text
    except Exception:
        pass
    return url, ""

def scrap(url):
    """Main scraping function - runs in a separate thread"""
    
    # Try to get URLs from sitemap first (recursively)
    sitemap_url = urljoin(url, "/sitemap.xml")
    urls = get_sitemap_urls_recursive(sitemap_url, max_urls=25)
    
    # If no sitemap found, crawl the site
    if not urls:
        urls = crawl_site(url, max_pages=15)
    
    if not urls:
        raise Exception("No URLs found for scraping")
    
    # Remove duplicates while preserving order
    seen = set()
    urls = [x for x in urls if not (x in seen or seen.add(x))]
    
    # Limit to maximum 25 URLs
    urls = urls[:10]
    
    saved_text = {}
    
    # Use ThreadPoolExecutor to process pages in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_url = {executor.submit(fetch_page_with_requests, url): url for url in urls}
        
        for future in concurrent.futures.as_completed(future_to_url):
            url = future_to_url[future]
            try:
                url_result, text = future.result()
                if text and len(text) > 100:  # Only save if we got meaningful content
                    saved_text[url_result] = text
            except Exception:
                pass
    
    return saved_text

def safe_text(text: str) -> str:
    return text.encode("latin-1", "ignore").decode("latin-1")
def scraped_data_to_pdf(saved_text, base_url, user_id):
    """Create PDF, store it in /tmp, and upload to GCS"""
    domain = urlparse(base_url).netloc.replace("www.", "").split(".")[0]
    pdf_name = f"{domain}.pdf"

    # Create local /tmp folder
    tmp_dir = "/tmp"
    os.makedirs(tmp_dir, exist_ok=True)

    pdf_path = os.path.join(tmp_dir, pdf_name)

    # Create PDF
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Arial", size=12)

    for url, text in saved_text.items():
        pdf.add_page()
        pdf.set_font_size(14)
        pdf.multi_cell(0, 10, f"URL: {url}")
        pdf.ln(5)
        pdf.set_font_size(11)
        clean_text = re.sub(r'\s+', ' ', text).strip()
        pdf.multi_cell(0, 8, safe_text(clean_text))

    # Save PDF locally
    pdf.output(pdf_path)

    # Upload to GCS
    gcs_url = None
    try:
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob_path = f"{user_id}/{pdf_name}"
        blob = bucket.blob(blob_path)

        # Upload local file to GCS
        blob.upload_from_filename(pdf_path, content_type="application/pdf")

        # Optionally make it public (or keep private if using IAM)
        gcs_url = blob.public_url
    except Exception as e:
        print(f"[WARN] GCS upload failed: {e}")

    return pdf_path, pdf_name, gcs_url


@router.get("/scrape")
async def scrape_endpoint(
    db: db_dependency,
    url: str = Query(..., description="URL to scrape"),
    current_user: dict = Depends(get_current_user),
):
    """API endpoint for website scraping — saves PDF locally + uploads to GCS"""
    try:
        # Ensure URL has a scheme
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        # Validate URL
        parsed_url = urlparse(url)
        if not parsed_url.netloc:
            raise HTTPException(status_code=400, detail="Invalid URL provided")
        
        # Run scraping
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(scrap, url)
            data = future.result(timeout=300)
        
        if not data:
            raise HTTPException(status_code=500, detail="No data could be scraped from the website")
        
        # Generate PDF (local + upload)
        pdf_path, pdf_filename, gcs_url = scraped_data_to_pdf(data, url, current_user["id"])
        
        # Save record in DB
        document = Documents(
            user_id=current_user['id'],
            doc_name=pdf_filename,
            doc_type="website"
        )
        db.add(document)
        db.commit()
        db.refresh(document)

        # Return FileResponse + GCS info
        return FileResponse(
            path=pdf_path,
            filename=pdf_filename,
            media_type="application/pdf"
        )

    except concurrent.futures.TimeoutError:
        raise HTTPException(status_code=504, detail="Scraping operation timed out")
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Scraping failed: {str(e)}")