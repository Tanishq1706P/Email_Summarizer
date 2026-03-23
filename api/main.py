from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.concurrency import run_in_threadpool
from pipeline import EmailSummarizationPipeline
from models.data_model import EmailDoc, UserFeedback, ErrorResponse, ErrorInfo, ErrorDetail
import os
import json
import uuid
import time
from logging_utils import setup_logging
from collections import defaultdict

# Setup structured logging
logger = setup_logging("api.main")

app = FastAPI(title="Email Summarizer Vercel API")

# API-6: Simple In-Memory Rate Limiting (Replace with Redis in Production)
RATE_LIMIT = 100 # requests per minute
request_counts = defaultdict(list)

def check_rate_limit(client_ip: str):
    now = time.time()
    # Filter requests in the last 60 seconds
    request_counts[client_ip] = [t for t in request_counts[client_ip] if now - t < 60]
    if len(request_counts[client_ip]) >= RATE_LIMIT:
        return False
    request_counts[client_ip].append(now)
    return True

# Check if we are running in Vercel
IS_VERCEL = os.environ.get("VERCEL") == "1"

# Initialize pipeline lazily to avoid blocking startup
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
    # API-6: Rate Limiting
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
    return {"message": "Email Summarizer API is running", "is_vercel": IS_VERCEL}

@app.post("/summarize", response_model=dict, responses={422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}})
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

@app.post("/feedback", responses={422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}})
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
    except Exception:
        return JSONResponse(status_code=503, content={"status": "not_ready"})
