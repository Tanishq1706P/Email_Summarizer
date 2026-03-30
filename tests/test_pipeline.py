import os
import sys

import pytest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from unittest.mock import MagicMock, patch

from models.data_model import EmailDoc
from pipelines.summarizer.pipeline import EmailSummarizationPipeline


@pytest.fixture
def mock_pipeline():
    with patch("pipelines.summarizer.pipeline.Generator"), patch(
        "pipelines.summarizer.pipeline.LearningStore"
    ), patch("pipelines.summarizer.ollama_local.LocalOllama") as MockLLM:
        MockLLM.return_value = MagicMock()
        p = EmailSummarizationPipeline()
        p._generator.generate.return_value = {
            "summary": "mock",
            "confidence": 0.9,
            "type": "BIZ",
            "priority": "Normal",
            "urgency": "LOW",
            "sentiment": "Neutral",
        }
        return p


def test_summarize(mock_pipeline):
    email = EmailDoc(id="1", text="test email")
    result = mock_pipeline.summarize(email)
    assert result.summary == "mock"
    assert result.confidence == 0.9
    assert result.pipeline.latency_ms > 0


def test_feedback(mock_pipeline):
    fb = MagicMock()
    result = mock_pipeline.feedback(fb)
    assert result is None  # No return value expected
