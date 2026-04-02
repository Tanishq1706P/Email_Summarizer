import os
import threading
import time
import uuid
from collections import defaultdict

from typing import Optional

import redis
from dotenv import load_dotenv
from fastapi import (
    Depends, FastAPI, HTTPException, Request,
    UploadFile, File, status, Body
)
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader

from logging_utils import setup_logging
from models.data_model import (
    BatchResult, BatchSummarizeRequest, EmailDoc,
    ErrorDetail, ErrorInfo, ErrorResponse,
    UserFeedback, List as ListModel
)
from pipelines.summarizer.pipeline import EmailSummarizationPipeline
from pipelines.summarizer.store_learning import LearningStore

import json

# ---------------- CONFIG ----------------
load_dotenv()
logger = setup_logging("api.main")

RATE_LIMIT = int(os.getenv("RATE_LIMIT", "100"))
REDIS_URL = os.getenv("REDIS_URL")
PRODUCTION_API_KEY = os.getenv("API_KEY", "").strip()
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

redis_client = None
if REDIS_URL:
    try:
        redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    except Exception:
        logger.warning("Redis connection failed")

app = FastAPI(title="Email Summarizer API")

# ---------------- CORS ----------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- API KEY ----------------
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_key(api_key: str = Depends(api_key_header)):
    if not api_key:
        raise HTTPException(401, "API key required")

    if not PRODUCTION_API_KEY:
        raise HTTPException(500, "API_KEY not configured")

    if api_key.strip() != PRODUCTION_API_KEY:
        raise HTTPException(403, "Invalid API key")

    return api_key

# ---------------- RATE LIMIT ----------------
def check_rate_limit(ip):
    if redis_client:
        try:
            key = f"rate:{ip}"
            count = redis_client.incr(key)
            if count == 1:
                redis_client.expire(key, 60)
            return count <= RATE_LIMIT
        except Exception:
            logger.warning("Redis rate limit fallback")
    return True

# ---------------- PIPELINE ----------------
pipeline = None

def get_pipeline():
    global pipeline
    if pipeline is None:
        logger.info("Initializing pipeline...")
        pipeline = EmailSummarizationPipeline()
    return pipeline

store = LearningStore()

# ---------------- MIDDLEWARE ----------------
@app.middleware("http")
async def middleware(request: Request, call_next):
    ip = request.client.host if request.client else "unknown"

    if not check_rate_limit(ip):
        return JSONResponse(status_code=429, content={"error": "Rate limit exceeded"})

    request.state.request_id = str(uuid.uuid4())
    start = time.perf_counter()

    response = await call_next(request)

    process_time = round((time.perf_counter() - start) * 1000, 2)
    response.headers["X-Process-Time"] = str(process_time)
    response.headers["X-Request-ID"] = request.state.request_id

    return response

# ---------------- HEALTH ----------------
@app.get("/health/live")
async def live():
    return {"status": "live"}

@app.get("/health/ready")
async def ready():
    try:
        get_pipeline()
        return {"status": "ready"}
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": str(e)})

# ---------------- UPLOAD ----------------
@app.post("/upload-emails", dependencies=[Depends(verify_api_key)])
async def upload_emails(
    file: UploadFile = File(None),
    emails: Optional[ListModel[EmailDoc]] = Body(None),
):
    if not store._use_mongo:
        raise HTTPException(500, "MongoDB not configured")

    try:
        if file:
            try:
                emails_data = json.loads(await file.read())
                if isinstance(emails_data, dict):
                    emails_data = [emails_data]
            except json.JSONDecodeError:
                raise HTTPException(400, "Invalid JSON in file")
        elif emails:
            emails_data = [e.model_dump() for e in emails]
        else:
            raise HTTPException(400, "Provide file or emails list")

        normalized = []

        for e in emails_data:
            if not isinstance(e, dict):
                continue
            text = e.get("text") or e.get("raw", "")

            # ✅ Extract important fields
            subject = e.get("subject")
            user_id = e.get("user_id")

            # ✅ Merge metadata safely
            metadata = e.get("metadata", {}) or {}

            if subject:
                metadata["subject"] = subject

            if user_id:
                metadata["user_id"] = user_id

            normalized.append({
                "text": text,
                "raw": e.get("raw"),
                "metadata": metadata
            })

        if not normalized:
            raise HTTPException(400, "No valid emails")

        inserted = store.insert_emails(normalized)

        return {
            "status": "success",
            "inserted": inserted,
            "received": len(normalized),
            "duplicates": len(normalized) - inserted
        }

    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(500, str(e))

# ---------------- SINGLE ----------------
@app.post("/summarize", dependencies=[Depends(verify_api_key)])
async def summarize(email: EmailDoc):
    if not email.text:
        raise HTTPException(400, "Empty email text")

    pipe = get_pipeline()

    result = pipe.summarize(email)

    # ALWAYS normalize
    if not isinstance(result, dict):
        result = result.model_dump()

    if not result or "summary" not in result:
        raise HTTPException(500, "Invalid summary result")

    updated = store.update_email_summary("summaries", email.id, result)

    logger.info(f"Single summary stored: {updated}")

    return result

# ---------------- BATCH ----------------
@app.post("/batch_summarize", response_model=BatchResult, dependencies=[Depends(verify_api_key)])
async def batch_summarize(req: BatchSummarizeRequest):

    emails = store.get_emails(req.collection, req.limit)

    if not emails:
        return BatchResult(success=True, processed=0, message="No emails found")

    results = []

    def safe_summarize(email):
        try:
            logger.info(f"Starting summarize for email_id: {email.id}, type: {type(email)}")
            
            pipe = get_pipeline()
            result = pipe.summarize(email)
            logger.info(f"Summarize complete for {email.id}. Result type: {type(result)}, keys: {list(result.keys()) if isinstance(result, dict) else 'N/A'}, has_session_id: {'session_id' in result if isinstance(result, dict) else False}")

            # ALWAYS normalize to dict
            if not isinstance(result, dict):
                logger.info(f"Converting result to dict via model_dump for {email.id}")
                result = result.model_dump()

            if not result or "summary" not in result:
                raise ValueError("Invalid summary output")

            logger.info(f"Storing summary for {email.id}")
            updated = store.update_email_summary(
                "summaries",
                email.id,
                result
            )
            logger.info(f"Store update result for {email.id}: {updated}")

            # success=false if no real summary
            has_real_summary = result.get("summary") is not None and len(str(result.get("summary", ""))) > 20 and "fallback" not in str(result.get("summary", "")).lower() and "excerpt" not in str(result.get("summary", "")).lower()
            summary_success = updated and has_real_summary
            logger.info(f"email {email.id}: updated={updated}, real_summary={has_real_summary}, success={summary_success}")

            return {
                "email_id": email.id,
                "success": summary_success,
                "session_id": result.get("session_id"),
                "has_real_summary": has_real_summary
            }

        except Exception as e:
            import traceback
            logger.error(f"Failed {getattr(email, 'id', 'unknown')}: {str(e)}\n{traceback.format_exc()}")
            return {
                "email_id": getattr(email, 'id', 'unknown'),
                "success": False,
                "error": str(e)
            }

    results = [safe_summarize(e) for e in emails]

    return BatchResult(
        success=True,
        processed=len(emails),
        results=results
    )

# ---------------- FEEDBACK ----------------
@app.post("/feedback", dependencies=[Depends(verify_api_key)])
async def feedback(fb: UserFeedback):
    pipe = get_pipeline()
    pipe.feedback(fb)
    return {"status": "feedback recorded"}
