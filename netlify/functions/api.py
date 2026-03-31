import os
import threading
import time
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import redis
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader

from logging_utils import setup_logging
from models.data_model import (
    BatchResult,
    BatchSummarizeRequest,
    EmailDoc,
    ErrorDetail,
    ErrorInfo,
    ErrorResponse,
    UserFeedback,
)
from pipeline import EmailSummarizationPipeline
from pipelines.summarizer.store_learning import LearningStore

# Setup structured logging
logger = setup_logging("api.main")

load_dotenv()

print("NOTE: CRLF .env detected. Fixed auth comparison to strip \\r")

# Early config for prints
RATE_LIMIT = int(os.environ.get("RATE_LIMIT", "100"))
REDIS_URL = os.environ.get("REDIS_URL")
redis_client = None
if REDIS_URL:
    try:
        redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    except Exception:
        redis_client = None
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "*").split(",")
PRODUCTION_API_KEY = os.environ.get("API_KEY")
IS_RENDER = os.environ.get("RENDER") == "true"

print("=== Email Summarizer Startup ===")
print(f"Mode: {'Render' if IS_RENDER else 'Local'}")
print(f"LLM: {'Groq (fast)' if os.environ.get('GROQ_API_KEY') else 'Ollama local'}")
print(
    f"Rate limit: {RATE_LIMIT}/min (Redis: {'enabled' if redis_client else 'fallback thread-safe'}"
)
print(f"Auth: {'required (X-API-Key)' if PRODUCTION_API_KEY else 'configure API_KEY'}")
print(f"CORS: {ALLOWED_ORIGINS[:2]}{'...' if len(ALLOWED_ORIGINS)>2 else ''}")
print("Endpoints ready. Health: /health/live /health/ready")
print("================================")

app = FastAPI(title="Email Summarizer Production API")

# ---- Security & Infrastructure Setup ----

# 1. CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. API Key Authentication
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


async def verify_api_key(api_key: str = Depends(api_key_header)):
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="API key required"
        )
    if not PRODUCTION_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API_KEY env var not configured",
        )
    if api_key != PRODUCTION_API_KEY.rstrip("\r"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key"
        )
    return api_key


# 3. Rate Limiting (Redis with In-Memory Fallback)
request_counts = defaultdict(list)
_count_lock = threading.Lock()


def check_rate_limit(client_ip: str) -> bool:
    now = time.time()

    # Try Redis first
    if redis_client:
        try:
            key = f"rate_limit:{client_ip}"
            current = redis_client.incr(key)
            if current == 1:
                redis_client.expire(key, 60)
            return current <= RATE_LIMIT
        except Exception as e:
            logger.warning(f"Redis rate limit check failed: {e}")

    # Thread-safe in-memory fallback
    with _count_lock:
        request_counts[client_ip] = [
            t for t in request_counts[client_ip] if now - t < 60
        ]
        if len(request_counts[client_ip]) >= RATE_LIMIT:
            return False
        request_counts[client_ip].append(now)
    return True


# ---- Application Logic ----
pipeline = None


def get_pipeline():
    global pipeline
    if pipeline is None:
        try:
            pipeline = EmailSummarizationPipeline()
        except Exception:
            logger.error("Failed to initialize pipeline", exc_info=True)
            raise RuntimeError("Pipeline initialization failed")
    return pipeline


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    details = [
        ErrorDetail(field=str(err["loc"]), issue=err["msg"]) for err in exc.errors()
    ]
    error_info = ErrorInfo(
        code="VALIDATION_ERROR",
        message="Request validation failed",
        details=details,
        request_id=(
            str(request.state.request_id)
            if hasattr(request.state, "request_id")
            else None
        ),
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ErrorResponse(error=error_info).model_dump(),
    )


@app.middleware("http")
async def security_and_telemetry_middleware(request: Request, call_next):
    client_ip = (
        request.client.host
        if hasattr(request.client, "host") and request.client.host
        else "unknown"
    )
    if not check_rate_limit(client_ip):
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"error": "Rate limit exceeded. Please wait 60s."},
            headers={"Retry-After": "60"},
        )

    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    start_time = time.perf_counter()

    response = await call_next(request)

    process_time = (time.perf_counter() - start_time) * 1000
    response.headers["X-Process-Time-MS"] = str(round(process_time, 2))
    response.headers["X-Request-ID"] = request_id

    # Security headers
    security_headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
        "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self' https://api.groq.com https://ollama.ai;",
    }
    for k, v in security_headers.items():
        response.headers[k] = v

    logger.info(
        "Request processed",
        extra={
            "props": {
                "request_id": request_id,
                "method": request.method,
                "url": str(request.url),
                "status_code": response.status_code,
                "duration_ms": process_time,
            }
        },
    )
    return response


@app.get("/")
async def read_root():
    return {"message": "Email Summarizer API is running", "is_render": IS_RENDER}


@app.post(
    "/summarize",
    response_model=dict,
    responses={422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    dependencies=[Depends(verify_api_key)],
)
async def summarize(email: EmailDoc, request: Request):
    if not email or not email.text or len(email.text) > 8000:
        raise HTTPException(status_code=413, detail="Email body too long or empty")
    try:
        pipe = await run_in_threadpool(get_pipeline)
        result = await run_in_threadpool(pipe.summarize, email)
        store = LearningStore()
        updated = store.update_email_summary("summaries", email.id, result)
        logger.info(f"Stored to summaries collection: {updated}")
        return result

    except RuntimeError as e:
        if "Circuit" in str(e):
            return JSONResponse(
                status_code=503,
                content={"error": "LLM service temporarily unavailable (Circuit Open)"},
            )
        raise
    except Exception as e:
        logger.error(
            "Summarization failed",
            extra={"props": {"request_id": getattr(request.state, "request_id", None)}},
            exc_info=True,
        )
        error_info = ErrorInfo(
            code="INTERNAL_SERVER_ERROR",
            message=str(e),
            request_id=getattr(request.state, "request_id", None),
        )
        return JSONResponse(
            status_code=500, content=ErrorResponse(error=error_info).model_dump()
        )


@app.post(
    "/feedback",
    responses={422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    dependencies=[Depends(verify_api_key)],
)
async def feedback(fb: UserFeedback, request: Request):
    try:
        pipe = await run_in_threadpool(get_pipeline)
        result = await run_in_threadpool(pipe.feedback, fb)
        return result
    except Exception as e:
        logger.error(
            "Feedback recording failed",
            extra={"props": {"request_id": request.state.request_id}},
            exc_info=True,
        )
        error_info = ErrorInfo(
            code="INTERNAL_SERVER_ERROR",
            message=str(e),
            request_id=request.state.request_id,
        )
        return JSONResponse(
            status_code=500, content=ErrorResponse(error=error_info).model_dump()
        )


@app.get("/health/live")
async def health_live():
    return {"status": "live"}


@app.get("/health/ready")
async def health_ready():
    try:
        await run_in_threadpool(get_pipeline)
        return {"status": "ready"}
    except Exception as e:
        logger.error(f"Health ready check failed: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=503, content={"status": "not_ready", "detail": str(e)}
        )


store = LearningStore()


@app.post(
    "/batch_summarize",
    response_model=BatchResult,
    dependencies=[Depends(verify_api_key)],
)
async def batch_summarize(batch_req: BatchSummarizeRequest, request: Request):
    """Batch summarize all emails from Mongo collection."""
    try:
        emails = await run_in_threadpool(
            store.get_emails, batch_req.collection, batch_req.limit
        )
        if not emails:
            return BatchResult(success=True, processed=0, message="No emails found")

        pipe = get_pipeline()
        results = []
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(pipe.summarize, email): email for email in emails
            }
            for future in as_completed(futures):
                email = futures[future]
                try:
                    result = future.result()
                    updated = store.update_email_summary(
                        batch_req.collection, email.id, result
                    )
                    results.append(
                        {
                            "email_id": email.id,
                            "success": updated,
                            "session_id": result.session_id,
                        }
                    )
                except Exception as e:
                    logger.error(f"Failed to summarize {email.id}: {e}")
                    results.append(
                        {"email_id": email.id, "success": False, "error": str(e)}
                    )

        logger.info(
            f"Batch summarize complete: {len([r for r in results if r['success']])}/{len(emails)}"
        )
        return BatchResult(success=True, processed=len(emails), results=results)
    except Exception as e:
        logger.error(f"Batch summarize failed: {e}", exc_info=True)
        return BatchResult(success=False, processed=0, message=str(e), error=str(e))
