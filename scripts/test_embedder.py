import sys
import os

# Add the project root to sys.path to allow imports
sys.path.append(os.getcwd())

from pipelines.summarizer.embedder import Embedder

def test_embedder():
    print("--- Testing Embedder ---")
    embedder = Embedder()
    
    # Test simple embedding
    test_text = "Hello, world!"
    print(f"Generating embedding for: '{test_text}'")
    embedding = embedder.get_embedding(test_text)
    
    if embedding:
        print("✔ Successfully generated embedding!")
        # It's a string representation of a list
        print(f"Embedding string (first 50 chars): {embedding[:50]}...")
    else:
        print("✘ Failed to generate embedding.")

    # Test combined subject and summary embedding
    subject = "Meeting Tomorrow"
    summary = "Reminder about our sync at 10 AM."
    print(f"Generating combined embedding for Subject: '{subject}' and Summary: '{summary}'")
    combined_embedding = embedder.embed_summary_and_subject(summary, subject)
    
    if combined_embedding:
        print("✔ Successfully generated combined embedding!")
    else:
        print("✘ Failed to generate combined embedding.")

if __name__ == "__main__":
    test_embedder()
