import logging
from fastapi import FastAPI
import inngest
import inngest.fast_api
from dotenv import load_dotenv
import uuid
import os
import datetime
import google.generativeai as genai 

# Import the specific embed function for queries
from data_loader import load_and_chunk_pdf, load_and_chunk_image, embed_texts, embed_query 
from vector_db import QdrantStorage
from custom_types import RAGChunkAndSrc, RAGUpsertResult, RAGSearchResult

load_dotenv()

# CHANGED: Configure Gemini
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

inngest_client = inngest.Inngest(
    app_id="rag_app",
    logger=logging.getLogger("uvicorn"),
    is_production=False,
    serializer=inngest.PydanticSerializer()
)

@inngest_client.create_function(
    fn_id="RAG: Ingest File",
    trigger=inngest.TriggerEvent(event="rag/ingest_file"),
    throttle=inngest.Throttle(
        limit = 2, period=datetime.timedelta(minutes=1)
    ),
    rate_limit=inngest.RateLimit(
        limit=1,
        period=datetime.timedelta(hours=4),
        key="event.data.source_id",
  ),
)
async def rag_ingest_file(ctx: inngest.Context):
    def _load(ctx: inngest.Context) -> RAGChunkAndSrc:
        file_path = ctx.event.data["file_path"]
        source_id = ctx.event.data.get("source_id", file_path)
        
        # Check file extension
        ext = os.path.splitext(file_path)[1].lower()
        if ext in ['.pdf']:
             chunks = load_and_chunk_pdf(file_path)
        elif ext in ['.png', '.jpg', '.jpeg']:
             chunks = load_and_chunk_image(file_path)
        else:
             chunks = [] # Or handle error
             
        return RAGChunkAndSrc(chunks=chunks, source_id=source_id)

    def _upsert(chunks_and_src: RAGChunkAndSrc) -> RAGUpsertResult:
        chunks = chunks_and_src.chunks
        source_id = chunks_and_src.source_id
        vecs = embed_texts(chunks)
        ids = [str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source_id}:{i}")) for i in range(len(chunks))]
        payloads = [{"source": source_id, "text": chunks[i]} for i in range(len(chunks))]
        QdrantStorage().upsert(ids, vecs, payloads)
        return RAGUpsertResult(ingested=len(chunks))

    chunks_and_src = await ctx.step.run("load-and-chunk", lambda: _load(ctx), output_type=RAGChunkAndSrc)
    ingested = await ctx.step.run("embed-and-upsert", lambda: _upsert(chunks_and_src), output_type=RAGUpsertResult)
    return ingested.model_dump()


@inngest_client.create_function(
    fn_id="RAG: Query PDF",
    trigger=inngest.TriggerEvent(event="rag/query_pdf_ai")
)
async def rag_query_pdf_ai(ctx: inngest.Context):
    
    # 1. Search Logic
    def _search(question: str, top_k: int = 5, file_names: list = None) -> RAGSearchResult:
        # CHANGED: Use the specific query embedding function from data_loader
        query_vec = embed_query(question) 
        store = QdrantStorage()
        found = store.search(query_vec, top_k, filter_sources=file_names)
        return RAGSearchResult(contexts=found["contexts"], sources=found["sources"])
    
    # 2. Generation Logic (Gemini 2.5 Flash)
    def _generate_answer(contexts: list, question: str) -> str:
        try:
            print(f"Generating answer for: {question}")
            model = genai.GenerativeModel('gemini-2.5-flash')
            
            context_block = "\n\n".join(f"- {c}" for c in contexts)
            
            prompt = f"""
            You are a PRECISE financial analyzer and advisor. Your goal is to help the user understand their bank statements and invoices with absolute clarity.
            
            ### INSTRUCTIONS:
            1.  **Use Markdown Tables**: Whenever you list transactions, spending categories, or summary data, ALWAYS use Markdown tables.
            2.  **Professional Structure**: Use clear headings (##) and bold text for emphasis.
            3.  **Visual Clarity**: If there are multiple items, group them logically. 
            4.  **Financial Advice**: Provide a separate section titled "## 💡 Financial Advice & Insights" with actionable steps.
            5.  **Data for Charts**: If you identify spending categories and their total amounts (e.g. Food: $200, Rent: $1000), please also provide a JSON block at the VERY END of your response (after all text) in the following format:
                ```json
                {{
                  "chart_data": [
                    {{"category": "Category1", "amount": 100.50}},
                    {{"category": "Category2", "amount": 250.00}}
                  ]
                }}
                ```
            6.  **Be Concise**: Avoid fluff. Focus on data and insight.

            Context from documents:
            {context_block}

            User Question: {question}
            
            Respond in a clear, professional format as if you are a high-end financial dashboard.
            """
            
            response = model.generate_content(prompt)
            print("Generation successful")
            return response.text
        except Exception as e:
            print(f"Error during generation: {e}")
            if hasattr(e, 'response') and hasattr(e.response, 'prompt_feedback'):
                print(f"Safety Feedback: {e.response.prompt_feedback}")
            return f"I apologize, but I encountered an error analyzing the document: {str(e)}"

    question = ctx.event.data["question"]
    top_k = int(ctx.event.data.get("top_k", 5))
    file_names = ctx.event.data.get("file_names", [])

    # Step 1: Retrieve
    found = await ctx.step.run("embed-and-search", lambda: _search(question, top_k, file_names), output_type=RAGSearchResult)

    # Step 2: Generate
    full_response = await ctx.step.run("generate-answer", lambda: _generate_answer(found.contexts, question))

    # Parse out JSON if present for charts
    import json
    chart_data = []
    answer = full_response
    if "```json" in full_response:
        try:
            parts = full_response.split("```json")
            answer = parts[0].strip()
            json_str = parts[1].split("```")[0].strip()
            data = json.loads(json_str)
            chart_data = data.get("chart_data", [])
        except Exception as e:
            print(f"Failed to parse chart data JSON: {e}")

    return {
        "answer": answer, 
        "sources": found.sources, 
        "num_contexts": len(found.contexts),
        "chart_data": chart_data
    }

app = FastAPI()

inngest.fast_api.serve(app, inngest_client, [rag_ingest_file, rag_query_pdf_ai])