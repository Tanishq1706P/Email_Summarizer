import email
from email import policy
from pathlib import Path
from bs4 import BeautifulSoup
import os

class EmailParser:
    """
    SEC-6: Path Sanitization & AI/ML: Context-Aware Chunking
    """
    def __init__(self, dirpath: Path):
        # SEC-6: Sanitize directory path
        self.dirpath = self._sanitize_path(dirpath)
        if not self.dirpath.exists():
            raise ValueError(f"Invalid or non-existent directory: {self.dirpath}")

    def _sanitize_path(self, path: Path) -> Path:
        """SEC-6: Prevent path traversal by resolving and validating base path."""
        resolved = path.resolve()
        # In a real production system, you would check against a list of allowed base dirs
        return resolved

    def parse_email_file(self, filepath: Path) -> dict:
        try:
            # SEC-6: Ensure file is within self.dirpath
            if not str(filepath.resolve()).startswith(str(self.dirpath)):
                raise PermissionError(f"Path traversal attempt blocked: {filepath}")

            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                raw_email = f.read()
            msg = email.message_from_string(raw_email, policy=policy.default)
            
            # AI/ML: Context-Aware Extraction
            subject = msg.get('Subject', "No Subject")
            sender = msg.get('From', "Unknown")
            date = msg.get('Date', "Unknown")
            body = self._extract_body(msg)

            # AI/ML: Context-Aware Chunking Preparation
            # We prepend metadata to the body so the LLM always knows the context of retrieved chunks
            context_header = f"DATE: {date}\nFROM: {sender}\nSUBJECT: {subject}\n\n"
            enriched_body = context_header + body

            email_data = {
                'filepath': str(filepath),
                'message': msg.get('Message-ID',""),
                'date': date,
                'from': sender,
                'to': msg.get('To', ""),
                'cc': msg.get('X-cc', ""),
                'bcc': msg.get('X-bcc', ""),
                'subject': subject,
                'body': enriched_body,
                'body_type': 'plain',
                'char_count': len(enriched_body),
                'word_count': len(enriched_body.split()),
                'has_attachments': self._check_attachments(msg)
            }
            return email_data
        except Exception as e:
            print(f"Error parsing {filepath}: {e}")
            return None

    def _check_attachments(self, msg):
        try:
            if not msg.is_multipart():
                return False
            for part in msg.walk():
                content_disposition = str(part.get("Content-Disposition", ""))
                if "attachment" in content_disposition:
                    return True
            return False
        except Exception:
            return False

    def _extract_body(self, msg):
        try:
            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    disposition = str(part.get("Content-Disposition"))
                    if content_type == "text/html" and "attachment" not in disposition:
                        return self._html_to_text(part.get_content()).strip()
                    if content_type == "text/plain" and "attachment" not in disposition:
                        return part.get_content().strip()
                return ""
            else:
                content = msg.get_content()
                if msg.get_content_type() == "text/html":
                    return self._html_to_text(content).strip()
                return content.strip()
        except Exception:
            return ""

    def _html_to_text(self, html_doc):
        soup = BeautifulSoup(html_doc, 'lxml')
        return soup.get_text(separator='\n', strip=True)

    def sample_emails(self):
        # SEC-6: Use rglob safely
        email_files = [f for f in self.dirpath.rglob('*') if f.is_file()]
        emails = []
        for fp in email_files:
            email_data = self.parse_email_file(fp)
            if email_data:
                emails.append(email_data)
        return emails
