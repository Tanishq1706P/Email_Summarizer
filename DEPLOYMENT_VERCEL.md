# Vercel & MongoDB Atlas Deployment Guide

Follow these steps to deploy your Email Summarizer API to Vercel with a MongoDB Atlas cloud database.

## Step 1: Set up MongoDB Atlas (Cloud Database)

1.  **Create an account**: Sign up at [mongodb.com/atlas](https://www.mongodb.com/cloud/atlas/lp/try2).
2.  **Create a Cluster**: Use the "Shared" (Free) tier. Choose a provider and region near your location.
3.  **Configure Network Access**:
    *   Go to **Network Access** > **Add IP Address**.
    *   Select **Allow Access From Anywhere** (IP `0.0.0.0/0`) since Vercel's IP addresses are dynamic.
4.  **Create Database User**:
    *   Go to **Database Access** > **Add New Database User**.
    *   Set a username and a strong password. Note these down.
5.  **Get Connection String**:
    *   Click **Connect** on your cluster.
    *   Select **Connect your application**.
    *   Copy the connection string (it looks like `mongodb+srv://<db_username>:<db_password>@cluster.mongodb.net/?retryWrites=true&w=majority`).
    *   Replace `<db_username>` and `<db_password>` with your user credentials.

## Step 2: Prepare the Codebase

1.  **Requirements**: Ensure `pymongo` and `sentence-transformers` are in your `requirements.txt`.
2.  **Vercel Configuration**: Your `vercel.json` is already configured to use the `@vercel/python` builder for `api/main.py`.

## Step 3: Deploy to Vercel

### Option A: Using Vercel Dashboard (Recommended)

1.  **Push code to GitHub**: Push your project to a GitHub repository.
2.  **Import to Vercel**:
    *   Login to [vercel.com](https://vercel.com).
    *   Click **Add New...** > **Project**.
    *   Import your GitHub repository.
3.  **Configure Environment Variables**:
    *   In the **Environment Variables** section, add the following:
        *   `MONGO_URI`: Your MongoDB Atlas connection string from Step 1.
        *   `MONGO_DB`: `email_summarizer` (or your preferred DB name).
        *   `LEARNING_ENABLED`: `true`
        *   `EMBEDDING_MODEL`: `all-MiniLM-L6-v2`
4.  **Deploy**: Click **Deploy**.

### Option B: Using Vercel CLI

1.  **Install CLI**: `npm i -g vercel`
2.  **Login**: `vercel login`
3.  **Deploy**: Run `vercel` in the project root.
4.  **Add Secrets**: Use `vercel env add MONGO_URI` to add your connection string.

## Step 4: Verification

1.  Once deployed, Vercel will provide a production URL (e.g., `https://your-project.vercel.app`).
2.  **Test the endpoint**: Send a POST request to `https://your-project.vercel.app/summarize` with a mock email JSON.
3.  **Check MongoDB**: Log in to MongoDB Atlas > **Browse Collections**. You should see a `sessions` collection with the new `vector_embedding` field.

## Troubleshooting

*   **Cold Starts**: The first request after deployment might be slow as Vercel downloads the `sentence-transformers` model. Subsequent requests will be much faster.
*   **Timeouts**: If Vercel times out (default is 10s for free tier), consider using a smaller model or optimizing the model loading in `api/main.py`.
