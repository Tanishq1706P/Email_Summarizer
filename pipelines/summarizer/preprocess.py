"""
Email Preprocessing - HTML Sanitization & Text Cleaning
Production-grade per elite standards
"""

import re

import html2text
from bleach import clean
from bs4 import BeautifulSoup


def preprocess_email_text(text: str, strip_html: bool = True) -> str:
    """
    Clean HTML from email body. Handles Outlook/Apple Mail/Gmail quirks.

    Args:
        text: Raw email body
        strip_html: If True, convert HTML to plain text (default)

    Returns:
        Clean plain text ready for LLM
    """
    if not text.strip():
        return text

    # Step 1: Bleach - Remove dangerous tags/scripts/styles
    cleaned = clean(
        text,
        tags=[
            "p",
            "br",
            "div",
            "span",
            "strong",
            "b",
            "em",
            "i",
            "u",
            "a",
            "li",
            "ul",
            "ol",
        ],
        strip=True,
    )

    # Step 2: BeautifulSoup - Fix malformed HTML (Outlook etc.)
    soup = BeautifulSoup(cleaned, "html.parser")

    # Preserve links as [text](url)
    for a in soup.find_all("a", href=True):
        link_text = a.get_text(strip=True) or "Link"
        a.string = f"[{link_text}]({a['href']})"
        a.unwrap()

    # Convert to plain text with smart line breaks
    h = html2text.HTML2Text()
    h.body_width = 0
    h.ignore_links = False
    h.ignore_images = True
    plain_text = h.handle(str(soup))

    # Step 3: Normalize whitespace/line breaks
    plain_text = re.sub(
        r"\n\s*\n\s*\n", "\n\n", plain_text
    )  # Collapse multiple newlines
    plain_text = re.sub(r"[ \t]+", " ", plain_text)  # Collapse spaces
    plain_text = plain_text.strip()

    return plain_text


def is_significant_html(text: str) -> bool:
    """
    Check if HTML is mostly formatting vs meaningful content.
    """
    soup = BeautifulSoup(text, "html.parser")
    text_nodes = soup.get_text()
    if len(text_nodes.strip()) < 50:
        return False
    return True
