import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
import os

# Set dummy API_KEY for testing
os.environ["API_KEY"] = "test-secret-key"

from api.main import app, get_pipeline
from models.data_model import EmailDoc, UserFeedback

client = TestClient(app)

# Mock Pipeline
class MockPipeline:
    def summarize(self, email: EmailDoc):
        return {
            "session_id": "mock-session-123",
            "email_id": email.id,
            "user_id": email.user_id or "unknown",
            "summary": "This is a mock summary.",
            "priority": "Normal",
            "urgency": "Normal",
            "sentiment": "Neutral"
        }
    
    def feedback(self, fb: UserFeedback):
        return {"status": "success", "session_id": fb.session_id}

@pytest.fixture
def mock_pipeline():
    with patch("api.main.get_pipeline") as mock:
        mock.return_value = MockPipeline()
        yield mock

def test_read_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Email Summarizer API is running", "is_render": False}

def test_health_live():
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "live"}

def test_health_ready(mock_pipeline):
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}

def test_summarize_auth_failure(mock_pipeline):
    email_data = {"id": "test", "text": "hello"}
    # No API Key
    response = client.post("/summarize", json=email_data)
    assert response.status_code == 403

def test_summarize_auth_success(mock_pipeline):
    email_data = {
        "id": "test-email-123",
        "text": "Hello, this is a test email.",
        "user_id": "test-user-456"
    }
    response = client.post("/summarize", 
                           json=email_data, 
                           headers={"X-API-Key": "test-secret-key"})
    assert response.status_code == 200
    assert response.json()["email_id"] == "test-email-123"

def test_feedback_auth_success(mock_pipeline):
    feedback_data = {
        "session_id": "mock-session-123",
        "rating": 5,
        "note": "Great summary!"
    }
    response = client.post("/feedback", 
                           json=feedback_data, 
                           headers={"X-API-Key": "test-secret-key"})
    assert response.status_code == 200
    assert response.json()["status"] == "success"

def test_cors_headers():
    test_origin = "http://localhost:3000"
    response = client.options("/summarize", headers={
        "Origin": test_origin,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "X-API-Key,Content-Type"
    })
    assert response.status_code == 200
    # FastAPI CORSMiddleware returns the origin if it matches allowed_origins (including *)
    assert response.headers["access-control-allow-origin"] == test_origin
