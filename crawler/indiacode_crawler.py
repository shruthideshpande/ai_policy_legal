import requests
from bs4 import BeautifulSoup
import time
import os
from urllib.parse import urljoin, urlparse

# --- Configuration ---
START_URL = "https://www.indiacode.nic.in/"
# Set to True to only list PDF URLs without downloading them.
# Set to False to actually download the files.
DRY_RUN = True
# Directory to save downloaded PDF files
DOWNLOAD_DIR = "downloaded_pdfs"
# Base URL needed to resolve relative links
BASE_URL = "https://www.indiacode.nic.in/"
# Be polite: Delay between requests
REQUEST_DELAY_SECONDS = 1
# Standard User-Agent to mimic a browser
# Some websites block requests that don't look like they come from a real browser.
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}
# --- /Configuration ---

# --- Global State (to avoid re-processing) ---
urls_to_visit = {START_URL}
visited_urls = set()

def is_valid_url(url):
    """Checks if a URL is valid and belongs to the target domain."""
    # urlparse breaks a URL into its components (scheme, domain, path, etc.).
    parsed = urlparse(url)
    # Ensure it's http/https, has a domain, and belongs to indiacode.nic.in
    return bool(parsed.scheme) and bool(parsed.netloc) and parsed.netloc == urlparse(BASE_URL).netloc

def get_page_content(url):
    """Fetches and returns the HTML content of a given URL."""
    print(f"Fetching: {url}")
    try:
        # The requests.get() function sends an HTTP GET request to the URL.
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status() # Check for HTTP errors
        # Be gentle
        time.sleep(REQUEST_DELAY_SECONDS)
        return response.content
    except requests.exceptions.RequestException as e:
        print(f"Error fetching {url}: {e}")
        return None

def download_pdf(pdf_url):
    """Downloads a PDF or, in dry run mode, just prints the URL."""
    if DRY_RUN:
        print(f"  [Dry Run] Found PDF: {pdf_url}")
        return

    # os.path.exists checks if a file or directory exists.
    # os.makedirs creates a directory, including any necessary parent directories.
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)

    # Generate a filename from the URL, ensuring it's valid
    file_name = pdf_url.split('/')[-1]
    if not file_name.endswith('.pdf'):
        file_name += ".pdf" # Ensure it has a .pdf extension
    # os.path.join creates a valid file path for the current operating system.
    file_path = os.path.join(DOWNLOAD_DIR, file_name)

    if os.path.exists(file_path):
        print(f"  [Skipping] Already downloaded: {file_name}")
        return

    print(f"  [Downloading] PDF from: {pdf_url}")
    try:
        # Use stream=True to download the file in chunks, which is memory-efficient for large files.
        response = requests.get(pdf_url, headers=HEADERS, timeout=60, stream=True)
        response.raise_for_status()
        with open(file_path, 'wb') as f:
            # response.iter_content() iterates over the response data in chunks.
            # This avoids loading the entire file into memory at once.
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"  [Success] Saved to {file_path}")
        time.sleep(REQUEST_DELAY_SECONDS) # Be polite after a download
    except requests.exceptions.RequestException as e:
        print(f"  [Error] Failed to download {pdf_url}: {e}")

def crawl_page(url):
    """
    Crawls a single page, finding new links to visit and PDF files to download.
    """
    global urls_to_visit, visited_urls

    if url in visited_urls:
        return

    visited_urls.add(url)
    html_content = get_page_content(url)

    if not html_content:
        return

    # BeautifulSoup parses the raw HTML content into a structured object.
    # 'html.parser' is a built-in Python HTML parser.
    soup = BeautifulSoup(html_content, 'html.parser')
    new_links_found = 0

    # soup.find_all('a', href=True) finds all anchor tags (<a>) that have an 'href' attribute.
    for link in soup.find_all('a', href=True):
        href = link['href']
        # urljoin intelligently combines the current page's URL with the found href
        # to create a full, absolute URL. .split('#')[0] removes page fragments.
        absolute_url = urljoin(url, href).split('#')[0]

        if not is_valid_url(absolute_url):
            continue

        if absolute_url.lower().endswith('.pdf'):
            download_pdf(absolute_url)
        elif absolute_url not in visited_urls and absolute_url not in urls_to_visit:
            urls_to_visit.add(absolute_url)
            new_links_found += 1
    
    if new_links_found > 0:
        print(f"  Found {new_links_found} new links to crawl.")

# --- Main Execution ---
if __name__ == "__main__":
    if DRY_RUN:
        print("--- Starting crawl in DRY RUN mode. PDFs will NOT be downloaded. ---")
    else:
        print("--- Starting crawl in DOWNLOAD mode. ---")
    print(f"PDFs will be saved to the '{DOWNLOAD_DIR}' directory.")
    
    while urls_to_visit:
        # .pop() gets an arbitrary element, which is fine for a set-based queue
        current_url = urls_to_visit.pop()
        crawl_page(current_url)
        print(f"Queue size: {len(urls_to_visit)} | Visited: {len(visited_urls)}")
    
    print("\n--- Crawl Finished ---")
    print(f"Visited a total of {len(visited_urls)} pages.")