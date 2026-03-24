#!/usr/bin/env python3
"""
Import Enron emails from maildir into MongoDB.
Converts .eml files to MongoDB documents.
"""

import os
import sys
from pathlib import Path
from email import message_from_file
from datetime import datetime
from pymongo import MongoClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "inbox")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "emails")

def parse_email_file(file_path: str) -> dict | None:
    """Parse .eml file and extract email data."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            msg = message_from_file(f)

        return {
            "file_path": str(file_path),
            "sender": msg.get("From", "unknown"),
            "recipient": msg.get("To", "unknown"),
            "cc": msg.get("Cc", ""),
            "subject": msg.get("Subject", ""),
            "date": msg.get("Date", ""),
            "body": msg.get_payload(decode=False) if isinstance(msg.get_payload(), str) else "",
            "imported_at": datetime.utcnow(),
        }
    except Exception as e:
        print(f"  [ERROR] Failed to parse {file_path}: {e}")
        return None

def import_from_maildir(maildir_path: str, limit: int = None):
    """Import emails from maildir directory structure into MongoDB."""

    # Connect to MongoDB
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB]
    collection = db[MONGO_COLLECTION]

    print(f"Connected to MongoDB: {MONGO_URI}/{MONGO_DB}/{MONGO_COLLECTION}")

    # Find all .eml files
    maildir = Path(maildir_path)
    eml_files = list(maildir.glob("**/*."))  # Enron emails have no extension

    if not eml_files:
        print(f"[ERROR] No email files found in {maildir_path}")
        return

    print(f"Found {len(eml_files)} email files to import")

    imported = 0
    skipped = 0

    for i, eml_file in enumerate(eml_files[:limit] if limit else eml_files):
        # Skip non-files
        if not eml_file.is_file():
            continue

        # Parse email
        email_doc = parse_email_file(str(eml_file))
        if not email_doc:
            skipped += 1
            continue

        # Check if already imported (by file_path)
        if collection.find_one({"file_path": email_doc["file_path"]}):
            skipped += 1
            continue

        # Insert into MongoDB
        try:
            collection.insert_one(email_doc)
            imported += 1

            if (imported + skipped) % 100 == 0:
                print(f"  Progress: {imported} imported, {skipped} skipped")

        except Exception as e:
            print(f"  [ERROR] Failed to insert {eml_file}: {e}")
            skipped += 1
    
    print(f"\n✔ Import complete!")
    print(f"  Imported: {imported}")
    print(f"  Skipped: {skipped}")
    print(f"  Total in collection: {collection.count_documents({})}")

    client.close()

if __name__ == "__main__":
    # Get maildir from env or default to data/raw/enron/maildir
    default_maildir = os.path.join(os.getcwd(), "data", "raw", "enron", "maildir")
    maildir = os.getenv("MAILDIR_PATH", default_maildir)
    
    # Override with command line arg if provided
    if len(sys.argv) > 1 and os.path.isdir(sys.argv[1]):
        maildir = sys.argv[1]
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
    else:
        limit = int(sys.argv[1]) if len(sys.argv) > 1 else None

    print("=" * 60)
    print("MongoDB Email Importer")
    print("=" * 60)

    if not Path(maildir).exists():
        print(f"[ERROR] Maildir not found: {maildir}")
        print(f"Please set MAILDIR_PATH env var or pass path as first argument.")
        sys.exit(1)

    import_from_maildir(maildir, limit)
