# Bank Statement & Invoice Analyzer

This application consists of three parts that need to be running simultaneously:

1. **FastAPI Backend**: Handles the AI logic and database operations.
2. **Inngest Dev Server**: Orchestrates the background jobs (ingestion and processing).
3. **Streamlit Frontend**: The user interface.

## Prerequisites

Ensure your `.env` file contains your `GOOGLE_API_KEY`.

## Step 1: Start the Backend

Open a terminal and run:

```powershell
uvicorn main:app --reload --port 8000
```

## Step 2: Start the Inngest Dev Server

Open a **new** terminal window and run:

```powershell
npx inngest-cli@latest dev -u http://127.0.0.1:8000/api/inngest
```

_This dashboard will be available at http://127.0.0.1:8288_

## Step 3: Start the Frontend

Open another **new** terminal window and run:

```powershell
streamlit run streamlit_app.py
```

## Usage

1. Open the Streamlit URL (usually http://localhost:8501).
2. **Upload** your Bank Statements (PDF) or Invoice Images (PNG/JPG) using the sidebar.
3. Click **"Process Files"** and wait for ingestion.
4. **Ask questions** in the chat (e.g., "What is the total spent on food?", "Analyze this invoice").
5. The AI will provide answers and financial advice.
6. Your **Chat History** is saved automatically and can be accessed from the sidebar.
