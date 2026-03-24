"""
Consolidated Data Models for Email Summarizer (Pydantic v2)
Source of truth for both API boundaries and internal pipeline logic.    
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


class EmailDoc(BaseModel):
    """Pre-masked email. Pipeline never sees raw PII."""
    id: str
    text: str
    user_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ActionItem(BaseModel):
    action:   str
    owner:    Optional[str] = None
    deadline: Optional[str] = None


class KeyDetails(BaseModel):
    dates:              List[str] = Field(default_factory=list)
    amounts:            List[str] = Field(default_factory=list)
    ids_and_references: List[str] = Field(default_factory=list)
    attachments:        List[str] = Field(default_factory=list)


class KeyEntities(BaseModel):
    people:        List[str] = Field(default_factory=list)
    organizations: List[str] = Field(default_factory=list)
    dates:         List[str] = Field(default_factory=list)


class Flags(BaseModel):
    confidential:            bool          = False
    context_gap:             bool          = False
    context_gap_note:        Optional[str] = None
    multilingual:            Optional[str] = None
    attachments_unretrieved: List[str]     = Field(default_factory=list)


class EvalScores(BaseModel):
    answer_relevance: float     = 0.0
    faithfulness:     float     = 0.0
    context_richness: float     = 0.0
    overall:          float     = 0.0
    passed:           bool      = False
    corrections:      int       = 0
    skipped:          bool      = False
    issues:           List[str] = Field(default_factory=list)


class PipelineMetadata(BaseModel):
    latency_ms:       float = 0.0
    eval_skipped:     bool  = False
    correction_count: int   = 0
    learned_rules:    int   = 0


class SummaryResult(BaseModel):
    """Complete output returned to the caller."""
    session_id: str
    email_id:   str
    user_id:    str

    type:           str
    category:       str
    summary:        str
    vector_embedding: Optional[str] = None
    action_items:   List[ActionItem] = Field(default_factory=list)      
    open_questions: List[str] = Field(default_factory=list)
    deadline:       Optional[str] = None

    priority:  str
    urgency:   str
    sentiment: str

    key_details:     KeyDetails = Field(default_factory=KeyDetails)     
    key_entities:    KeyEntities = Field(default_factory=KeyEntities)   
    type_enrichment: Dict[str, Any] = Field(default_factory=dict)       
    flags:           Flags = Field(default_factory=Flags)
    confidence:      float = 0.0

    eval:     EvalScores       = Field(default_factory=EvalScores)      
    pipeline: PipelineMetadata = Field(default_factory=PipelineMetadata)
    metadata: Dict[str, Any]   = Field(default_factory=dict)


class UserFeedback(BaseModel):
    """Feedback submitted by the user after reviewing a summary."""     
    session_id:       str
    rating:           int
    correction:       Optional[str] = None
    missing_items:    List[str]      = Field(default_factory=list)      
    tone_off:         bool           = False
    wrong_priority:   bool           = False
    wrong_type:       bool           = False
    note:             Optional[str] = None


class ErrorDetail(BaseModel):
    field: Optional[str] = None
    issue: str


class ErrorInfo(BaseModel):
    code: str
    message: str
    details: List[ErrorDetail] = Field(default_factory=list)
    request_id: Optional[str] = None


class ErrorResponse(BaseModel):
    error: ErrorInfo
