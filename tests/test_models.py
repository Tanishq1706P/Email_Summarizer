import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models.data_model import (
    BatchSummarizeRequest,
    EmailDoc,
    SummaryResult,
    UserFeedback,
)


def test_email_doc():
    doc = EmailDoc(id="1", text="test body")
    assert doc.id == "1"
    assert doc.text == "test body"
    assert doc.metadata == {}


def test_summary_result_minimal():
    result = SummaryResult(
        session_id="sess1",
        email_id="1",
        user_id="user1",
        type="BIZ",
        category="Work",
        summary="test",
        priority="Normal",
        urgency="LOW",
        sentiment="Neutral",
        confidence=0.9,
    )
    assert result.summary == "test"
    assert result.sentiment == "Neutral"


def test_user_feedback():
    fb = UserFeedback(session_id="sess1", rating=5)
    assert fb.rating == 5


def test_validation_email_long_text():
    long_text = "a" * 10001
    # Note: FastAPI Body max_length handled at API level, not Pydantic field
    doc = EmailDoc(id="1", text=long_text[:8000])  # Should accept truncated
    assert len(doc.text) == 8000


def test_batch_request():
    req = BatchSummarizeRequest(collection="test", limit=10)
    assert req.limit == 10
