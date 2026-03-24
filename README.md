# Email AI Assistant - Backend Server

An AI-powered email summarization and metadata extraction server that helps users manage their inbox more efficiently. It extracts key information, identifies action items, and learns from user feedback to improve future summaries.

## Key Features

- **Automated Summarization**: Generates concise summaries of long emails using LLMs.
- **Action Item Extraction**: Identifies and extracts tasks, deadlines, and open questions.
- **Email Categorization**: Automatically classifies emails by type (e.g., MEETING, ACTION, INFO) and category (e.g., Coordination, Billing).
- **Adaptive Learning**: Injects learned rules from user feedback to refine future outputs.
- **Hybrid Search**: Supports semantic search via vector embeddings and keyword search.
- **Rate Limiting & Reliability**: Built-in rate limiting and circuit breaker for robust production use.

## Tech Stack

- **Framework**: [FastAPI](https://fastapi.tiangolo.com/) (Python 3.10+)
- **LLM Inference**: [Ollama](https://ollama.com/) (Local) or OpenAI (Optional)
- **Embeddings**: [Sentence-Transformers](https://www.sbert.net/) (`all-MiniLM-L6-v2`)
- **Vector Database**: [Qdrant](https://qdrant.tech/)
- **Primary Database**: [MongoDB](https://www.mongodb.com/) (Sessions, Metadata, Feedback)
- **Caching & Rate Limiting**: [Redis](https://redis.io/)
- **Infrastructure**: [Docker](https://www.docker.com/) & [Docker Compose](https://docs.docker.com/compose/)
- **Data Versioning**: [DVC](https://dvc.org/)
- **Deployment**: [Vercel](https://vercel.com/) (Serverless)

## Server Flow

1.  **Request Ingestion**: Receives raw email data (subject, body, sender, etc.) via the `/summarize` endpoint.
2.  **Adaptive Rule Injection**: Fetches previously learned user preferences and instructions from the `LearningStore`.
3.  **LLM Generation**: Processes the email and learned rules to generate a structured summary, category, priority, and action items.
4.  **Evaluation & Correction**: (Optional/Training Mode) Validates the output and performs self-correction if necessary.
5.  **Vector Embedding**: Generates a semantic vector embedding for the summary and subject to enable efficient search.
6.  **Persistence**: Stores the session data, metadata, and embeddings in MongoDB and Qdrant.
7.  **Feedback Loop**: When users provide feedback via `/feedback`, the `AdaptiveLearner` updates the `LearningStore` with new rules.

## Setup & Installation

### 1. Prerequisites

- Python 3.10 or higher
- [Docker](https://docs.docker.com/get-docker/) & [Docker Compose](https://docs.docker.com/compose/install/)
- [Ollama](https://ollama.com/) (installed and running on host)

### 2. Clone the Repository

```bash
git clone <repository-url>
cd Android_Email_Project
```

### 3. Install Dependencies

```bash
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Configure Environment

Copy the example environment file and update the variables:

```bash
cp .env.example .env
```

Ensure `OLLAMA_HOST` and `MONGO_URI` are correctly configured.

### 5. Start Infrastructure

Run the setup script to start MongoDB, Qdrant, and Redis containers:

```bash
./setup_infra.sh
```

### 6. Run the Server

Start the FastAPI server:

```bash
./run_server.sh
```

Or manually using uvicorn:

```bash
uvicorn api.main:app --reload --port 8000
```

## API Endpoints

- `GET /`: Health check.
- `POST /summarize`: Summarize an email. Expects an `EmailDoc` JSON body. **Requires `X-API-Key` header**.
- `POST /feedback`: Submit user feedback for a summary session. **Requires `X-API-Key` header**.
- `GET /health/live`: Liveness check.
- `GET /health/ready`: Readiness check.