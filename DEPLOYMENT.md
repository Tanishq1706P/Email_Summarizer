# Production Deployment Guide: Email Summarizer API

This guide provides step-by-step instructions for deploying the Email Summarizer API to production.

## Prerequisites
- A managed **MongoDB** instance (e.g., MongoDB Atlas).
- A managed **Redis** instance (e.g., Upstash, Redis Cloud).
- A managed **Qdrant** instance (e.g., Qdrant Cloud).
- An LLM hosting solution (e.g., OpenAI API, or self-hosted Ollama on a GPU instance).

## Step 1: Prepare Your Infrastructure
1. **MongoDB**: Create a cluster and get your MONGO_URI. Ensure the database name matches your configuration (default: email_summarizer).
2. **Redis**: Get your REDIS_URL. This is used for distributed rate limiting.
3. **Qdrant**: Get your QDRANT_HOST and any necessary API keys.
4. **LLM**:
   - If using **Ollama**, deploy it on a GPU instance and get its public URL (set as OLLAMA_HOST).
   - If switching to **OpenAI**, you will need to modify pipelines/summarizer/ollama_local.py to use the OpenAI client.

## Step 2: Configure Environment Variables
Set the following environment variables on your hosting platform (Render, Vercel, Railway, etc.):

| Variable | Description | Example |
|----------|-------------|---------|
| API_KEY | **Required** Secret key for API authentication. | your-secure-api-key |
| MONGO_URI | MongoDB connection string. | mongodb+srv://user:pass@cluster.mongodb.net/ |
| REDIS_URL | Redis connection string for rate limiting. | edis://default:pass@redis-host:6379 |
| OLLAMA_HOST | URL of your Ollama or LLM server. | http://your-ollama-server:11434 |
| ALLOWED_ORIGINS | Comma-separated list of allowed CORS origins. | https://your-frontend.com |
| RATE_LIMIT | Max requests per IP per minute (default: 100). | 50 |
| LLM_MODEL | The LLM model name to use. | qwen2.5:1.5b |

## Step 3: Deployment Options

### Option A: Render (Recommended)
Render is ideal for this project as it supports Docker and long-running processes.
1. Create a new **Web Service** on Render.
2. Connect your GitHub repository.
3. Select **Docker** as the environment.
4. Add the environment variables from Step 2.
5. Render will automatically use the Dockerfile to build and deploy your API.

### Option B: Docker (Self-Hosted)
If you have your own VPS:
1. Copy the code to your server.
2. Build the image: docker build -t email-summarizer-api .
3. Run the container:
   `ash
   docker run -d -p 8000:8000 \
     -e API_KEY=your-key \
     -e MONGO_URI=your-mongo-uri \
     -e REDIS_URL=your-redis-url \
     email-summarizer-api
   `

## Step 4: Verification
1. Test the root endpoint:
   `ash
   curl https://your-app-url.com/
   `
2. Test a protected endpoint (requires API key):
   `ash
   curl -X POST https://your-app-url.com/summarize \
     -H "X-API-Key: your-secure-api-key" \
     -H "Content-Type: application/json" \
     -d '{"id": "test", "text": "Hello world"}'
   `

## Security Best Practices
- **Rotate API Keys**: Periodically update your API_KEY.
- **Restrict CORS**: Never leave ALLOWED_ORIGINS as * in production.
- **Monitoring**: Use Render's built-in logs or a service like Datadog to monitor for INTERNAL_SERVER_ERROR (500) responses.
