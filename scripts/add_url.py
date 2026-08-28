import asyncio
import argparse
import os
import subprocess
from datetime import datetime
import httpx
from bs4 import BeautifulSoup
from fetch_rss import SYSTEM_PROMPT, slugify

def extract_content(html):
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.string if soup.title else "Untitled URL"
    for script in soup(["script", "style", "nav", "header", "footer"]):
        script.extract()
    text = soup.get_text(separator="\n", strip=True)
    return title, text

async def process_url(url, source_name):
    print(f"Fetching URL: {url}")
    async with httpx.AsyncClient() as client:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = await client.get(url, headers=headers, follow_redirects=True)
        response.raise_for_status()
        html = response.text

    title, raw_text = extract_content(html)
    iso_date = datetime.now().isoformat()
    slug = slugify(title)
    if not slug:
        slug = "manual-" + str(hash(url))
        
    filename = f"src/content/posts/{slug}.md"
    if os.path.exists(filename):
        print(f"Skipping, '{filename}' already exists.")
        return

    print(f"Title extracted: {title}")
    
    prompt = f"""
{SYSTEM_PROMPT}

Please process the following article from a manually submitted URL.

Title: {title}
Original URL: {url}
Publish Date: {iso_date}
Source: {source_name}

Content:
{raw_text[:25000]}
"""

    print("Spawning Antigravity Agent for processing (via agy CLI)...")
    
    result = subprocess.run(["agy", "--print", prompt], capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"Error invoking agy: {result.stderr}")
        return
        
    output = result.stdout.strip()
    
    if output.startswith("```markdown"):
        output = output[11:]
    if output.startswith("```"):
        output = output[3:]
    if output.endswith("```"):
        output = output[:-3]
    output = output.strip()
    
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "w", encoding="utf-8") as f:
        f.write(output)
        
    print(f"Saved: {filename}")

def main():
    parser = argparse.ArgumentParser(description="Manually add a URL to sumai")
    parser.add_argument("url", help="The URL to fetch and summarize")
    parser.add_argument("--source", default="manual", help="The source tag for the article")
    args = parser.parse_args()
    
    asyncio.run(process_url(args.url, args.source))

if __name__ == "__main__":
    main()
