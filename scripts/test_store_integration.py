import sys
import os
import json
from pathlib import Path

# Add the project root to sys.path to allow imports
sys.path.append(os.getcwd())

from pipelines.summarizer.store_learning import LearningStore
from models.data_model import EmailDoc, SummaryResult, EvalScores, PipelineMetadata

def test_store_integration():
    print("--- Testing LearningStore Integration ---")
    
    # Use a temporary JSON file for testing if MongoDB fails
    test_json_path = "test_learning_store.json"
    if os.path.exists(test_json_path):
        os.remove(test_json_path)
    
    # Initialize LearningStore
    store = LearningStore(path=test_json_path)
    
    # Create mock email
    email = EmailDoc(
        id="test-email-123",
        text="Can we have a sync meeting tomorrow at 10 AM to discuss the project?",
        metadata={"subject": "Project Sync"}
    )
    
    # Create mock SummaryResult
    result = SummaryResult(
        session_id="test-session-456",
        email_id="test-email-123",
        user_id="test-user-789",
        type="MEETING",
        category="Coordination",
        summary="Request for a sync meeting tomorrow at 10 AM.",
        priority="Normal",
        urgency="Normal",
        sentiment="Neutral",
        confidence=0.95,
        eval=EvalScores(overall=0.9, passed=True),
        pipeline=PipelineMetadata(latency_ms=150.0)
    )
    
    # Record the session (this should trigger embedding generation)
    print("Recording session in LearningStore...")
    store.record_session(result.session_id, email, result)
    
    # Verify the stored data
    if store._use_mongo:
        print("✔ LearningStore is using MongoDB. Fetching session from MongoDB...")
        session = store._db.sessions.find_one({"session_id": result.session_id})
    else:
        print(f"✔ LearningStore fell back to JSON. Checking {test_json_path}...")
        store.flush(force=True)
        with open(test_json_path, 'r') as f:
            data = json.load(f)
            session = data.get("sessions", {}).get(result.session_id)
    
    if session:
        print("✔ Session found in store!")
        vector_embedding = session.get("vector_embedding")
        if vector_embedding:
            print("✔ vector_embedding field found!")
            print(f"Embedding string (first 50 chars): {vector_embedding[:50]}...")
        else:
            print("✘ vector_embedding field MISSING in stored data.")
    else:
        print("✘ Session NOT found in store.")

if __name__ == "__main__":
    test_store_integration()
