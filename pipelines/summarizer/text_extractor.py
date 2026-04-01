import re
import html
from bs4 import BeautifulSoup
from typing import Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import email

def extract_text(raw_email: str) -> str:
    """
    Extract clean plain text from raw email (MIME/HTML/plain).
    Handles multipart/alternative, HTML → text conversion.
    """
    if not raw_email:
        return ''
    
    try:
        # Try parsing as MIME message first
        msg = email.message_from_string(raw_email)
        
        # Walk MIME parts for text content
        def get_text_from_part(part):
            if part.get_content_type() == 'text/plain':
                return part.get_payload(decode=True).decode('utf-8', errors='ignore')
            elif part.get_content_type() == 'text/html':
                soup = BeautifulSoup(part.get_payload(decode=True), 'html.parser')
                # Extract text, preserve structure
                for script in soup(['script', 'style']):
                    script.decompose()
                text = soup.get_text(separator='\\n', strip=True)
                return re.sub(r'\\n{3,}', '\\n\\n', text)
            elif part.get_content_maintype() == 'multipart':
                # Recurse into multipart
                text_parts = []
                for subpart in part.get_payload():
                    text_parts.append(get_text_from_part(subpart))
                return '\\n\\n'.join([t for t in text_parts if t.strip()])
            return ''
        
        text = get_text_from_part(msg)
        if text.strip():
            return text.strip()
        
    except Exception:
        pass  # Fallback to simpler extraction
    
    # Fallback: simple extraction (headers + body)
    # Remove headers (first double newline)
    body_start = raw_email.find('\\n\\n')
    if body_start > 0:
        body = raw_email[body_start+2:].strip()
    else:
        body = raw_email
    
    # Strip HTML tags, decode entities
    soup = BeautifulSoup(body, 'html.parser')
    text = soup.get_text(separator='\\n', strip=True)
    
    # Clean whitespace
    text = re.sub(r'\\s+', ' ', text)
    text = re.sub(r'\\n{3,}', '\\n\\n', text)
    
    return text[:8000]  # Truncate for LLM limits

