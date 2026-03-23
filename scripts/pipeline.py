import json
from pathlib import Path
import os
from typing import List, Dict, Any
from scripts.email_parser import EmailParser
from scripts.sampler import StratifiedSampler
from scripts.scorer import score_json


def save_emails_to_json(emails: List[Dict[str, Any]], output_json: str) -> None:
    """
    Save parsed emails to a JSON file.

    Args:
        emails: List of email dictionaries
        output_json: Path to output JSON file
    """
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(emails, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(emails)} emails to {output_json}")


def append_emails_to_json(emails: List[Dict[str, Any]], output_json: str) -> None:
    """
    Append parsed emails to a JSON file (creates file if it doesn't exist).

    Args:
        emails: List of email dictionaries
        output_json: Path to output JSON file
    """
    existing_emails = []

    # Load existing data if file exists
    if os.path.exists(output_json):
        try:
            with open(output_json, 'r', encoding='utf-8') as f:
                existing_emails = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            existing_emails = []

    # Append new emails
    existing_emails.extend(emails)

    # Save back to file
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(existing_emails, f, indent=2, ensure_ascii=False)

    print(f"Appended {len(emails)} emails. Total: {len(existing_emails)}")


if __name__ == "__main__":
    # JSON output paths
    CLEANED_JSON = "data/processed/cleaned_emails.json"
    SAMPLED_JSON = "data/processed/sampled_dataset.json"
    FINAL_JSON = "data/processed/final_dataset.json"

    # Ensure directories exist
    os.makedirs("data/processed", exist_ok=True)

    # Parse emails from raw maildir and save to JSON
    base_path = Path('data/raw/enron/maildir/')
    
    if base_path.exists():
        all_folders = sorted([f for f in base_path.iterdir() if f.is_dir()], key=lambda x: x.name)
        # Limit to 75 folders for processing
        processing_folders = all_folders[:75]
        print(f"Processing {len(processing_folders)} folders...")

        for user_folder in processing_folders:
            target_dir = user_folder / "all_documents"
            if target_dir.exists():
                print(f"Processing: {user_folder.name}")
                parser = EmailParser(target_dir)
                parsed_emails = parser.sample_emails()

                if parsed_emails:
                    append_emails_to_json(parsed_emails, CLEANED_JSON)
    else:
        print(f"Skipping parsing: {base_path} not found.")

    # Stratified sampling - now using JSON
    if os.path.exists(CLEANED_JSON):
        sampler = StratifiedSampler()
        print("\n📊 Running stratified sampling...")
        sampler.stratified_sample_json(
            CLEANED_JSON,
            SAMPLED_JSON
        )
    else:
        print(f"Skipping sampling: {CLEANED_JSON} not found.")

    # Priority scoring - now using JSON
    if os.path.exists(SAMPLED_JSON):
        print("\n🎯 Running priority scoring...")
        score_json(
            input_json=SAMPLED_JSON,
            output_json=FINAL_JSON
        )
    else:
        print(f"Skipping scoring: {SAMPLED_JSON} not found.")

    print("\n✅ Pipeline complete!")
    print(f"  - Parsed emails: {CLEANED_JSON if os.path.exists(CLEANED_JSON) else 'None'}")
    print(f"  - Sampled dataset: {SAMPLED_JSON if os.path.exists(SAMPLED_JSON) else 'None'}")
    print(f"  - Final dataset with priorities: {FINAL_JSON if os.path.exists(FINAL_JSON) else 'None'}")
