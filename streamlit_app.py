import asyncio
import time
import uuid
import streamlit as st
import inngest
import requests
import os
from pathlib import Path
from dotenv import load_dotenv
from storage import save_chat, get_chat, load_chats, rename_chat
import pandas as pd
import plotly.express as px

load_dotenv()

# --- Configuration ---
st.set_page_config(page_title="Bank Statement Analyzer", page_icon="💳", layout="wide")

# Google Fonts & Custom CSS
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    /* Global Font */
    html, body, [class*="css"], .stMarkdown {
        font-family: 'Inter', system-ui, -apple-system, sans-serif !important;
    }

    /* Sidebar Styling - ChatGPT Style */
    [data-testid="stSidebar"] {
        background-color: #171717 !important;
        border-right: 1px solid #2d2d2d;
    }
    
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
        padding-top: 0rem;
        gap: 0;
    }

    /* Navigation Items Style */
    .nav-item {
        display: flex;
        align-items: center;
        padding: 8px 12px;
        border-radius: 8px;
        color: #ececec;
        font-size: 14px;
        transition: background 0.1s;
        text-decoration: none;
        margin-bottom: 2px;
    }
    .nav-item:hover {
        background-color: #2f2f2f;
    }
    .nav-icon {
        margin-right: 12px;
        width: 20px;
        text-align: center;
    }

    /* Heading Style */
    .sidebar-heading {
        color: #b4b4b4;
        font-size: 12px;
        font-weight: 600;
        margin: 18px 12px 8px 12px;
        letter-spacing: 0.2px;
    }

    /* Hidden elements */
    [data-testid="stHeader"] {
        background-color: transparent !important;
    }
    [data-testid="stSidebarNav"] {
        display: none;
    }

    /* Custom Input Styling (Search) */
    .stTextInput input {
        background-color: transparent !important;
        border: 1px solid #333 !important;
        color: #ddd !important;
    }

    /* Chat Button Overrides */
    .stButton button {
        background-color: transparent;
        border: none;
        text-align: left;
        color: #ececec;
        padding: 8px 12px;
        width: 100%;
        font-weight: 400;
        display: block;
        margin-bottom: 2px;
    }
    .stButton button:hover {
        background-color: #2f2f2f !important;
        color: white;
    }
    
    /* Active message highlight */
    [data-testid="stChatMessage"] {
        background-color: transparent !important;
        border-bottom: 1px solid #2d2d2d;
        border-radius: 0;
    }
</style>
""", unsafe_allow_html=True)

# --- Inngest Client ---
@st.cache_resource
def get_inngest_client() -> inngest.Inngest:
    return inngest.Inngest(app_id="rag_app", is_production=False)

def _inngest_api_base() -> str:
    return os.getenv("INNGEST_API_BASE", "http://127.0.0.1:8288/v1")

# --- Helper Functions ---
def fetch_runs(event_id: str) -> list[dict]:
    url = f"{_inngest_api_base()}/events/{event_id}/runs"
    try:
        resp = requests.get(url)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [])
    except Exception:
        return []

def wait_for_run_output(event_id: str, timeout_s: float = 120.0, poll_interval_s: float = 0.5) -> dict:
    start = time.time()
    last_status = None
    while True:
        runs = fetch_runs(event_id)
        if runs:
            run = runs[0]
            status = run.get("status")
            last_status = status or last_status
            if status in ("Completed", "Succeeded", "Success", "Finished"):
                return run.get("output") or {}
            if status in ("Failed", "Cancelled"):
                raise RuntimeError(f"Function run {status}")
        if time.time() - start > timeout_s:
            raise TimeoutError(f"Timed out waiting for run output (last status: {last_status})")
        time.sleep(poll_interval_s)

def save_uploaded_file(file) -> Path:
    uploads_dir = Path("uploads")
    uploads_dir.mkdir(parents=True, exist_ok=True)
    file_path = uploads_dir / file.name
    file_path.write_bytes(file.getbuffer())
    return file_path

async def send_rag_ingest_event(file_path: Path) -> None:
    client = get_inngest_client()
    await client.send(
        inngest.Event(
            name="rag/ingest_file",
            data={
                "file_path": str(file_path.resolve()),
                "source_id": file_path.name,
            },
        )
    )

async def send_rag_query_event(question: str, top_k: int, file_names: list = None) -> str:
    client = get_inngest_client()
    result = await client.send(
        inngest.Event(
            name="rag/query_pdf_ai",
            data={
                "question": question,
                "top_k": top_k,
                "file_names": file_names or [],
            },
        )
    )
    return result[0]

# --- Session State Management ---
if "current_chat_id" not in st.session_state:
    st.session_state.current_chat_id = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "processed_files" not in st.session_state:
    st.session_state.processed_files = []

# --- Sidebar ---
with st.sidebar:
    st.markdown("<h2 style='margin-bottom: 20px; font-weight: 700;'>💳 Finance AI</h2>", unsafe_allow_html=True)
    
    # Navigation
    if st.button("📝 New chat", use_container_width=True):
        st.session_state.current_chat_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.session_state.processed_files = [] # Reset files for the new chat
        st.rerun()

    # Search Bar
    search_query = st.text_input("🔍 Search chats", placeholder="Search...", label_visibility="collapsed")

    st.markdown("<div class='sidebar-heading'>Your chats</div>", unsafe_allow_html=True)
    
    chats = load_chats()
    chats.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    
    # Filter chats if searching
    if search_query:
        chats = [c for c in chats if search_query.lower() in c.get("title", "").lower()]

    # History list with Edit capability
    for chat in chats:
        col1, col2 = st.columns([0.8, 0.2])
        
        with col1:
            title = chat.get("title", "Untitled Chat")
            display_title = (title[:22] + '...') if len(title) > 22 else title
            if st.button(display_title, key=f"btn_{chat['id']}", use_container_width=True):
                st.session_state.current_chat_id = chat["id"]
                st.session_state.messages = chat["messages"]
                st.rerun()
        
        with col2:
            with st.popover("✏️"):
                new_title = st.text_input("Rename Chat", value=chat.get("title", ""), key=f"rename_{chat['id']}")
                if st.button("Save", key=f"save_{chat['id']}"):
                    rename_chat(chat["id"], new_title)
                    st.rerun()

    # Fixed bottom area for uploads
    st.markdown("<div style='margin-top: 30px;'>", unsafe_allow_html=True)
    st.divider()
    with st.expander("📂 Upload & Analyze"):
        # Use a dynamic key to reset the uploader on "New Chat"
        uploader_key = f"uploader_{st.session_state.current_chat_id}"
        uploaded_files = st.file_uploader(
            "Upload Documents", 
            type=["pdf", "png", "jpg", "jpeg"], 
            accept_multiple_files=True,
            label_visibility="collapsed",
            key=uploader_key
        )
        if uploaded_files:
            if st.button("⚡ Process Files", use_container_width=True):
                with st.spinner("Processing..."):
                    for uploaded in uploaded_files:
                        path = save_uploaded_file(uploaded)
                        asyncio.run(send_rag_ingest_event(path))
                        if uploaded.name not in st.session_state.processed_files:
                            st.session_state.processed_files.append(uploaded.name)
                    st.success("Ready!")
    st.markdown("</div>", unsafe_allow_html=True)

# --- Main Interface ---

# Initialize chat if needed
if not st.session_state.current_chat_id:
    st.session_state.current_chat_id = str(uuid.uuid4())

# Display Title
st.markdown("<h1 style='text-align: center; margin-top: -50px;'>Bank Statement & Invoice Analyzer</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #888; margin-bottom: 40px;'>Ask questions about your finances. I will analyze your uploaded documents and give advice.</p>", unsafe_allow_html=True)

# Display Chat History
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        
        # Display Charts if present
        if "chart_data" in msg and msg["chart_data"]:
            df = pd.DataFrame(msg["chart_data"])
            col1, col2 = st.columns(2)
            with col1:
                fig_bar = px.bar(df, x="category", y="amount", title="Spending by Category", color="category")
                fig_bar.update_layout(showlegend=False)
                st.plotly_chart(fig_bar, use_container_width=True)
            with col2:
                fig_pie = px.pie(df, values="amount", names="category", title="Spending Distribution")
                st.plotly_chart(fig_pie, use_container_width=True)

        if "sources" in msg and msg["sources"]:
            with st.expander("Reference Sources"):
                for s in msg["sources"]:
                    st.write(f"- {s}")

# Chat Input
if prompt := st.chat_input("Ask about your statement or invoice..."):
    # Add User Message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Generate Response
    with st.chat_message("assistant"):
        with st.spinner("📊 Analyzing data..."):
            try:
                # Pass currently processed files for filtering
                event_id = asyncio.run(send_rag_query_event(prompt, top_k=5, file_names=st.session_state.processed_files))
                output = wait_for_run_output(event_id)
                answer = output.get("answer", "I couldn't generate an answer.")
                sources = output.get("sources", [])
                chart_data = output.get("chart_data", [])
                
                st.markdown(answer)
                
                # Display Charts
                if chart_data:
                    df = pd.DataFrame(chart_data)
                    col1, col2 = st.columns(2)
                    with col1:
                        fig_bar = px.bar(df, x="category", y="amount", title="Spending by Category", color="category")
                        fig_bar.update_layout(showlegend=False)
                        st.plotly_chart(fig_bar, use_container_width=True)
                    with col2:
                        fig_pie = px.pie(df, values="amount", names="category", title="Spending Distribution")
                        st.plotly_chart(fig_pie, use_container_width=True)

                if sources:
                    with st.expander("Reference Sources"):
                         for s in sources:
                            st.write(f"- {s}")
                
                # Add Assistant Message
                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": answer,
                    "sources": sources,
                    "chart_data": chart_data
                })
                
                # Save Chat
                title = st.session_state.messages[0]["content"][:30] + "..." if st.session_state.messages else "New Chat"
                save_chat(st.session_state.current_chat_id, title, st.session_state.messages)

            except Exception as e:
                st.error(f"An error occurred: {e}")