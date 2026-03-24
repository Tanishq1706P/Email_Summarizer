from fastapi import FastAPI, HTTPException, Request, status, Depends
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pipeline import EmailSummarizationPipeline
from models.data_model import EmailDoc, UserFeedback, ErrorResponse, ErrorInfo, ErrorDetail
import os
import json
import uuid
import time
import redis
from logging_utils import setup_logging
from collections import defaultdict

# Setup structured logging
logger = setup_logging("api.main")

app = FastAPI(title="Email Summarizer Production API")

# ---- Security & Infrastructure Setup ----

# 1. CORS Configuration
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "*").split(",")
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
PRODUCTION_API_KEY = os.environ.get("API_KEY")

async def verify_api_key(api_key: str = Depends(api_key_header)):
    # Skip auth in development if no API_KEY is set
    if not PRODUCTION_API_KEY:
        return api_key
    if api_key != PRODUCTION_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials"
        )
    return api_key

# 3. Rate Limiting (Redis with In-Memory Fallback)
RATE_LIMIT = int(os.environ.get("RATE_LIMIT", "100"))
REDIS_URL = os.environ.get("REDIS_URL")
redis_client = None

if REDIS_URL:
    try:
        redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        logger.info("Redis rate limiting enabled")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")

# In-memory fallback
request_counts = defaultdict(list)

def check_rate_limit(client_ip: str):
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

    # In-memory fallback
    request_counts[client_ip] = [t for t in request_counts[client_ip] if now - t < 60]
    if len(request_counts[client_ip]) >= RATE_LIMIT:
        return False
    request_counts[client_ip].append(now)
    return True

# ---- Application Logic ----

IS_RENDER = os.environ.get("RENDER") == "true"
pipeline = None

def get_pipeline():
    global pipeline
    if pipeline is None:
        try:
            pipeline = EmailSummarizationPipeline()
        except Exception as e:
            logger.error("Failed to initialize pipeline", exc_info=True)        
            raise RuntimeError("Pipeline initialization failed")
    return pipeline

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    details = [ErrorDetail(field=str(err["loc"]), issue=err["msg"]) for err in exc.errors()]
    error_info = ErrorInfo(
        code="VALIDATION_ERROR",
        message="Request validation failed",
        details=details,
        request_id=str(request.state.request_id) if hasattr(request.state, "request_id") else None
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ErrorResponse(error=error_info).model_dump()
    )

@app.middleware("http")
async def security_and_telemetry_middleware(request: Request, call_next):       
    client_ip = request.client.host if request.client else "unknown"
    if not check_rate_limit(client_ip):
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"error": "Rate limit exceeded. Please wait 60s."}
        )

    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    start_time = time.perf_counter()

    response = await call_next(request)

    process_time = (time.perf_counter() - start_time) * 1000
    response.headers["X-Process-Time-MS"] = str(round(process_time, 2))
    response.headers["X-Request-ID"] = request_id

    logger.info(
        "Request processed",
        extra={"props": {
            "request_id": request_id,
            "method": request.method,
            "url": str(request.url),
            "status_code": response.status_code,
            "duration_ms": process_time
        }}
    )
    return response

@app.get("/")
async def read_root():
    return {"message": "Email Summarizer API is running", "is_render": IS_RENDER}

@app.post("/summarize", 
          response_model=dict, 
          responses={422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
          dependencies=[Depends(verify_api_key)])
async def summarize(email: EmailDoc, request: Request):
    try:
        pipe = await run_in_threadpool(get_pipeline)
        result = await run_in_threadpool(pipe.summarize, email)
        return result
    except RuntimeError as e:
        if "Circuit" in str(e):
            return JSONResponse(status_code=503, content={"error": "LLM service temporarily unavailable (Circuit Open)"})
        raise
    except Exception as e:
        logger.error("Summarization failed", extra={"props": {"request_id": request.state.request_id}}, exc_info=True)
        error_info = ErrorInfo(
            code="INTERNAL_SERVER_ERROR",
            message=str(e),
            request_id=request.state.request_id
        )
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(error=error_info).model_dump()
        )

@app.post("/feedback", 
          responses={422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
          dependencies=[Depends(verify_api_key)])
async def feedback(fb: UserFeedback, request: Request):
    try:
        pipe = await run_in_threadpool(get_pipeline)
        result = await run_in_threadpool(pipe.feedback, fb)
        return result
    except Exception as e:
        logger.error("Feedback recording failed", extra={"props": {"request_id": request.state.request_id}}, exc_info=True)
        error_info = ErrorInfo(
            code="INTERNAL_SERVER_ERROR",
            message=str(e),
            request_id=request.state.request_id
        )
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(error=error_info).model_dump()
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
        return JSONResponse(status_code=503, content={"status": "not_ready", "detail": str(e)})
