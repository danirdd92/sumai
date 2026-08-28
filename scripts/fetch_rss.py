import asyncio
import argparse
import feedparser
import yaml
import os
import glob
import re
import subprocess
from datetime import datetime
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

SYSTEM_PROMPT = """You are a Principal Technical Editor and Senior DevOps Engineer. Your task is to process technical blog posts, documentation, or tutorials and synthesize them into streamlined, high-signal, production-ready articles. 

Your articles must be strictly **unslopified**: devoid of marketing fluff, introductory clichés, redundant explanations, and superficial summaries. 

---
# Core Guidelines
1. Strip Non-Essential Information: Remove personal anecdotes, historical context unless strictly architecturally relevant, sponsor messages, and repetitive phrasing. Cut out basic definitions of standard industry terms.
2. Streamline & Clarify: Focus entirely on how it works, why it matters, architectural trade-offs, and implementation details. Use concise, direct language.
3. Provide Concrete Examples: Every abstract concept or architectural pattern must be backed by a minimal, working code snippet, configuration file, or ASCII diagram. Code must be idiomatic and production-ready.
4. Preserve Nuance (Unslopified): Do not oversimplify complex trade-offs. Highlight drawbacks and failure modes explicitly.

---
# Output Format
You must output a single Markdown file containing YAML frontmatter enclosed in `---`.
The frontmatter MUST include exactly these fields:
title: "[Title provided]"
originalUrl: "[URL provided]"
publishDate: [Date provided in ISO format]
source: "[Source provided]"
tags: [Array of 3-5 inferred technical topics, e.g., ["networking", "ebpf", "security"]]

The body of the Markdown should be the processed article.
DO NOT output anything else. DO NOT wrap the output in markdown code blocks (e.g. ```markdown). Start immediately with `---`.
"""


def clean_html(html_content):
    soup = BeautifulSoup(html_content, "html.parser")
    return soup.get_text(separator="\n", strip=True)


def slugify(text):
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def get_scraped_urls():
    scraped_urls = set()
    for filename in glob.glob("src/content/posts/*.md"):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                content = f.read()
                if content.startswith("---"):
                    end_idx = content.find("---", 3)
                    if end_idx != -1:
                        frontmatter = content[3:end_idx]
                        try:
                            fm = yaml.safe_load(frontmatter)
                            if fm and "originalUrl" in fm:
                                scraped_urls.add(fm["originalUrl"])
                        except yaml.YAMLError:
                            pass
        except Exception:
            pass
    return scraped_urls


async def process_entry(entry, source_name, scraped_urls):
    title = entry.get("title", "Untitled")
    link = entry.get("link", "")

    if link in scraped_urls:
        print(f"Skipping '{title}', URL already scraped.")
        return

    date_str = (
        entry.get("published") or entry.get("updated") or datetime.now().isoformat()
    )
    try:
        dt = date_parser.parse(date_str)
        iso_date = dt.isoformat()
    except Exception:
        iso_date = datetime.now().isoformat()

    slug = slugify(title)
    if not slug:
        slug = "post-" + str(hash(link))

    filename = f"src/content/posts/{slug}.md"

    # Even if URL is new, if slug exists we should append a hash to avoid overwriting a different post with same title
    if os.path.exists(filename):
        slug = f"{slug}-{hash(link) % 10000}"
        filename = f"src/content/posts/{slug}.md"
        if os.path.exists(filename):
             print(f"Skipping '{title}', slug already exists.")
             return

    print(f"Processing: {title} from {source_name}")

    content_html = ""
    if "content" in entry:
        content_html = entry["content"][0].get("value", "")
    elif "summary" in entry:
        content_html = entry["summary"]

    raw_text = clean_html(content_html)

    prompt = f"""
{SYSTEM_PROMPT}

Please process the following blog post.

Title: {title}
Original URL: {link}
Publish Date: {iso_date}
Source: {source_name}

Content:
{raw_text[:25000]}
"""

    print("Spawning Antigravity Agent for processing (via agy CLI)...")

    # We use agy --print to leverage the user's Antigravity IDE subscription
    # automatically, bypassing the need for a Developer API Key.
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
    
    # Add to in-memory set in case of duplicates within same run
    scraped_urls.add(link)
    
    print(f"Saved: {filename}")


async def main():
    parser = argparse.ArgumentParser(description="Fetch RSS feeds and summarize")
    parser.add_argument(
        "--year", type=int, default=datetime.now().year, help="Filter articles by year"
    )
    args = parser.parse_args()

    target_year = args.year

    try:
        with open("feeds.yaml", "r") as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        print("feeds.yaml not found.")
        return

    feeds = config.get("feeds", [])
    if not feeds:
        print("No feeds found in feeds.yaml")
        return

    scraped_urls = get_scraped_urls()
    print(f"Found {len(scraped_urls)} previously scraped URLs.")

    for feed_item in feeds:
        url = feed_item.get("url")
        source = feed_item.get("source", "unknown")
        print(f"Fetching RSS: {url}")

        parsed = feedparser.parse(url)
        for entry in parsed.entries:
            date_str = entry.get("published") or entry.get("updated") or ""
            try:
                dt = date_parser.parse(date_str)
                if dt.year != target_year:
                    continue
            except Exception:
                continue

            await process_entry(entry, source, scraped_urls)


if __name__ == "__main__":
    asyncio.run(main())
