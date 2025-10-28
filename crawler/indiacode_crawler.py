import requests
from bs4 import BeautifulSoup
import time
import os
from urllib.parse import urljoin, urlparse

from google.cloud import storage
from google.api_core import exceptions

# --- Configuration ---
START_URL = "https://www.indiacode.nic.in/"
# Set to True to only list PDF URLs without downloading them.
# Read from environment variables, with fallbacks for local execution.
# In Cloud Run, we will set these variables.
PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "aipolicylegal")
BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME", "indiacode-pdfs-v1")
# Set the DRY_RUN environment variable to "false" to download files.
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() != "false"

# File in GCS to store the set of visited URLs to allow for resuming.
VISITED_URLS_BLOB_NAME = "crawler_state/visited_urls.txt"
# Local file to buffer newly visited URLs before uploading.
NEWLY_VISITED_URLS_FILE = "newly_visited_urls.txt"

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
# This set will be populated from GCS at the start of the script.
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

def download_and_upload_pdf(pdf_url: str, bucket: storage.Bucket):
    """Downloads a PDF from a URL and uploads it to a GCS bucket."""
    if DRY_RUN:
        print(f"  [Dry Run] Found PDF: {pdf_url}")
        return

    try:
        # Extract filename from URL
        parsed_url = urlparse(pdf_url)
        file_name = os.path.basename(parsed_url.path)
        if not file_name:
            print(f"Could not determine filename for {pdf_url}. Skipping.")
            return

        blob = bucket.blob(file_name)

        if blob.exists():
            print(f"  [Skipping] Already exists in GCS: {file_name}")
            return

        print(f"  [Downloading] PDF from: {pdf_url}")
        response = requests.get(pdf_url, headers=HEADERS, timeout=60)
        response.raise_for_status() # Raise an exception for bad status codes

        print(f"  [Uploading] '{file_name}' to GCS bucket '{bucket.name}'...")
        blob.upload_from_string(
            response.content, content_type="application/pdf"
        )

        print(f"  [Success] Uploaded '{file_name}'.")
        time.sleep(REQUEST_DELAY_SECONDS) # Be polite after a download
    except requests.exceptions.RequestException as e:
        print(f"  [Error] Failed to download or upload {pdf_url}: {e}")
    except exceptions.GoogleAPICallError as e:
        print(f"  [Error] Failed to upload to GCS: {e}")

def crawl_page(url: str, bucket: storage.Bucket):
    """
    Crawls a single page, finding new links to visit and PDF files to download.
    """
    global urls_to_visit, visited_urls

    if url in visited_urls or url in urls_to_visit:
        return

    visited_urls.add(url)
    # Write newly visited URL to a local file to be uploaded in batches.
    with open(NEWLY_VISITED_URLS_FILE, "a") as f:
        f.write(url + "\n")

    html_content = get_page_content(url)

    # The URL has been processed, remove it from the to-do list.
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
            download_and_upload_pdf(absolute_url, bucket)
        elif absolute_url not in visited_urls and absolute_url not in urls_to_visit:
            urls_to_visit.add(absolute_url)
            new_links_found += 1
    
    if new_links_found > 0:
        print(f"  Found {new_links_found} new links to crawl.")

def upload_visited_urls(bucket: storage.Bucket):
    """Appends newly visited URLs to the master list in GCS."""
    if not os.path.exists(NEWLY_VISITED_URLS_FILE):
        return

    print("\n--- Syncing visited URLs to GCS ---")
    blob = bucket.blob(VISITED_URLS_BLOB_NAME)

    try:
        # GCS doesn't have a native append. We simulate it by downloading the
        # existing file, appending new URLs, and re-uploading.
        existing_urls = blob.download_as_text() if blob.exists() else ""
        with open(NEWLY_VISITED_URLS_FILE, "r") as f:
            new_urls = f.read()

        combined_urls = existing_urls + new_urls
        blob.upload_from_string(combined_urls, content_type="text/plain")
        os.remove(NEWLY_VISITED_URLS_FILE) # Clear the local buffer
        print("--- Sync complete ---\n")
    except (exceptions.GoogleAPICallError, OSError) as e:
        print(f"  [Error] Failed to sync visited URLs to GCS: {e}")
# --- Main Execution ---
if __name__ == "__main__":
    if DRY_RUN:
        print("--- Starting crawl in DRY RUN mode. PDFs will NOT be downloaded. ---")
    else:
        print("--- Starting crawl in DOWNLOAD mode. ---")
        print(f"PDFs will be uploaded to the GCS bucket 'gs://{BUCKET_NAME}'.")

    # Initialize the GCS client
    storage_client = storage.Client(project=PROJECT_ID)

    try:
        # Get the bucket object
        bucket = storage_client.get_bucket(BUCKET_NAME)
    except exceptions.NotFound:
        print(f"Error: Bucket '{BUCKET_NAME}' not found.")
        print("Please create the GCS bucket before running the script.")
        exit()

    # --- Load State ---
    print(f"Attempting to load previously visited URLs from 'gs://{BUCKET_NAME}/{VISITED_URLS_BLOB_NAME}'...")
    visited_urls_blob = bucket.blob(VISITED_URLS_BLOB_NAME)
    try:
        if visited_urls_blob.exists():
            # Download the list of URLs visited in previous runs.
            previous_urls = visited_urls_blob.download_as_text().splitlines()
            visited_urls.update(previous_urls)
            print(f"Loaded {len(previous_urls)} visited URLs from previous session.")
        else:
            print("No previous session found. Starting a new crawl.")
    except exceptions.GoogleAPICallError as e:
        print(f"Could not load visited URLs from GCS: {e}. Starting fresh.")

    # Remove already visited URLs from the initial queue.
    urls_to_visit.difference_update(visited_urls)

    # --- Crawl Loop ---
    pages_since_last_sync = 0
    try:
        while urls_to_visit:
            # .pop() gets an arbitrary element, which is fine for a set-based queue
            current_url = urls_to_visit.pop()
            crawl_page(current_url, bucket)
            pages_since_last_sync += 1
            print(f"Queue size: {len(urls_to_visit)} | Visited: {len(visited_urls)}")

            # Periodically save progress to GCS
            if pages_since_last_sync >= 10:
                upload_visited_urls(bucket)
                pages_since_last_sync = 0
    finally:
        # Ensure final state is saved on exit or interruption (e.g., Ctrl+C)
        print("\n--- Crawl interrupted or finished. Saving final state... ---")
        upload_visited_urls(bucket)
        print(f"Visited a total of {len(visited_urls)} pages.")
        print(f"You can now create a Vertex AI Search data store from the GCS bucket 'gs://{BUCKET_NAME}'.")