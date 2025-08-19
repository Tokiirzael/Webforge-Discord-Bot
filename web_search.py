import os
import requests
from serpapi import GoogleSearch
from bs4 import BeautifulSoup
from config import SERPAPI_API_KEY_NAME

def perform_search(query: str):
    """
    Performs a web search using SerpApi and returns a list of organic results.
    """
    api_key = os.getenv(SERPAPI_API_KEY_NAME)
    if not api_key:
        print(f"Error: {SERPAPI_API_KEY_NAME} not found in environment variables.")
        return None

    params = {
        "q": query,
        "api_key": api_key,
    }

    try:
        search = GoogleSearch(params)
        results = search.get_dict()
        organic_results = results.get("organic_results", [])
        return organic_results
    except Exception as e:
        print(f"An error occurred during web search: {e}")
        return None

def scrape_website_text(url: str):
    """
    Scrapes the main text content from a given URL.
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')

        # Remove script and style elements
        for script_or_style in soup(["script", "style"]):
            script_or_style.decompose()

        # A simple approach: get all text from the body
        text = soup.body.get_text()

        # Break into lines and remove leading/trailing space on each
        lines = (line.strip() for line in text.splitlines())
        # Break multi-headlines into a line each
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        # Drop blank lines
        text = '\n'.join(chunk for chunk in chunks if chunk)

        return text.strip()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL {url}: {e}")
        return None
    except Exception as e:
        print(f"An error occurred during web scraping: {e}")
        return None
