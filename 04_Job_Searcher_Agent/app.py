import os
import io
import sys
import asyncio
import streamlit as st
import logging
from datetime import datetime
import time

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

from config.settings import settings
from models.search_config import SearchConfig
from controllers.search_controller import SearchController
from controllers.export_controller import ExportController
from views.components import render_sidebar, render_results_header, render_job_table
from services.applied_store import AppliedStore

if sys.platform == "win32":
    proactor_policy = getattr(asyncio, "WindowsProactorEventLoopPolicy", None)
    if proactor_policy is not None:
        try:
            asyncio.set_event_loop_policy(proactor_policy())
        except Exception:
            pass

# ─── Page Config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Job Hunter AI",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Light theme override for readability */
    .stApp {
        background: #ffffff;
        color: #111111;
    }
    .stApp [data-testid="stMarkdownContainer"] {
        color: #111111;
    }
    .stApp p, .stApp div, .stApp span, .stApp label {
        color: #111111;
    }

    .main-title {
        font-size: 2.4rem;
        font-weight: 800;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0;
    }
    .subtitle {
        font-size: 1rem;
        color: #888;
        margin-top: 0;
        margin-bottom: 1.5rem;
    }
    .stButton > button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.5rem 2rem;
        font-size: 1rem;
        font-weight: 600;
        transition: all 0.2s;
    }
    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
    }
    .metric-card {
        background: #1a1a2e;
        border-radius: 10px;
        padding: 1rem;
        text-align: center;
    }
    a { text-decoration: none !important; }
    .status-box {
        background: #ffffff;
        color: #111111;
        border: 1px solid #e6e8ee;
        border-left: 4px solid #667eea;
        padding: 0.75rem 1rem;
        border-radius: 0 8px 8px 0;
        margin-bottom: 0.5rem;
        font-size: 0.9rem;
    }
    .skill-chip {
        display: inline-block;
        padding: 6px 10px;
        margin: 6px 8px 0 0;
        border-radius: 999px;
        border: 1px solid #e6e8ee;
        background: #f8fafc;
        color: #111111;
        font-size: 0.85rem;
        font-weight: 600;
        line-height: 1;
    }
</style>
""", unsafe_allow_html=True)

# ─── Session State Init ──────────────────────────────────────────────────────
if "jobs" not in st.session_state:
    st.session_state.jobs = []
if "search_done" not in st.session_state:
    st.session_state.search_done = False
if "csv_filepath" not in st.session_state:
    st.session_state.csv_filepath = None
if "applied_store_path" not in st.session_state:
    st.session_state.applied_store_path = None

# ─── Header ─────────────────────────────────────────────────────────────────
st.markdown('<p class="main-title">🎯 Job Hunter AI</p>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">Scrape Naukri, Foundit & more · AI-Powered Analysis · Tech Stack · Joining Period · Export CSV</p>', unsafe_allow_html=True)

# ─── Sidebar Config ─────────────────────────────────────────────────────────
config: SearchConfig = render_sidebar()

# ─── Search Button ───────────────────────────────────────────────────────────
col_btn, col_reset, _ = st.columns([2, 1, 6])
search_clicked = col_btn.button("🚀 Hunt Jobs", use_container_width=True)
if col_reset.button("🔄 Reset", use_container_width=True):
    st.session_state.jobs = []
    st.session_state.search_done = False
    st.session_state.csv_filepath = None
    st.rerun()

# ─── Search Execution ────────────────────────────────────────────────────────
if search_clicked:
    if not config.sources:
        st.error("Please select at least one job source.")
    elif not config.keywords and not config.locations and not config.tech_stacks and not config.candidate_resume_text:
        st.warning("Please provide at least one search criterion (keywords, location, tech stack, or upload your resume).")
    else:
        st.session_state.jobs = []
        st.session_state.search_done = False

        status_placeholder = st.empty()
        progress_bar = st.progress(0)
        eta_placeholder = st.empty()
        log_messages = []
        t0 = time.time()
        last_progress = {"p": 0.0}

        def update_progress(msg: str):
            # Parse structured progress messages from controller:
            # "__PROGRESS__:0.420:message"
            if isinstance(msg, str) and msg.startswith("__PROGRESS__:"):
                try:
                    _, p_str, rest = msg.split(":", 2)
                    p = float(p_str)
                    p = max(0.0, min(1.0, p))
                    progress_bar.progress(int(p * 100))
                    last_progress["p"] = p
                    elapsed = max(0.001, time.time() - t0)
                    if p > 0.02:
                        eta_s = int(elapsed * (1 - p) / p)
                        eta_placeholder.caption(f"Elapsed: {int(elapsed)}s • ETA: ~{eta_s}s")
                    msg = rest
                except Exception:
                    pass
            log_messages.append(msg)
            with status_placeholder.container():
                for m in log_messages[-5:]:
                    st.markdown(f'<div class="status-box">{m}</div>', unsafe_allow_html=True)

        update_progress("⚡ Starting job search...")

        controller = SearchController(config)
        jobs = controller.run(progress_callback=update_progress)
        progress_bar.progress(max(80, int(last_progress["p"] * 100)))

        if jobs:
            applied_store = AppliedStore()
            applied_store.apply_to_jobs(jobs)

            # Auto-export CSV
            exporter = ExportController()
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_path = exporter.export_to_csv(jobs, filename=f"jobs_{ts}.csv")
            st.session_state.csv_filepath = csv_path
            st.session_state.applied_store_path = applied_store.filepath
            progress_bar.progress(100)
            update_progress(f"✅ Done! Found {len(jobs)} jobs. CSV saved: {csv_path}")
        else:
            update_progress("⚠️ No jobs found. Try broader search criteria.")
            progress_bar.progress(100)

        st.session_state.jobs = jobs
        st.session_state.search_done = True

# ─── Results ─────────────────────────────────────────────────────────────────
if st.session_state.search_done and st.session_state.jobs:
    jobs = st.session_state.jobs

    # Source breakdown
    from collections import Counter
    source_breakdown = dict(Counter(j.source for j in jobs))
    render_results_header(len(jobs), source_breakdown)

    # Show what the resume extraction identified (if any)
    if config.keywords or config.tech_stacks:
        st.markdown("### 🧠 What I identified from your resume")
        c1, c2 = st.columns([2, 6])
        with c1:
            st.caption("Primary Keywords / Role")
            st.write(config.keywords or "—")
        with c2:
            st.caption("Skills & Technologies")
            if config.tech_stacks:
                chips = "".join([f'<span class="skill-chip">{st}</span>' for st in config.tech_stacks])
                st.markdown(chips, unsafe_allow_html=True)
            else:
                st.write("—")
        st.markdown("---")

    # Controls row
    ctrl1, ctrl2, ctrl3 = st.columns([2, 2, 4])
    filter_source = ctrl1.selectbox("Filter by Source", ["All"] + list(source_breakdown.keys()))
    sort_option = ctrl2.selectbox("Sort By", ["Relevance Score ↓", "Posted Date ↓", "Company A-Z", "Immediate Joining First"])

    # Apply filters
    filtered = jobs
    if filter_source != "All":
        filtered = [j for j in jobs if j.source == filter_source]

    if sort_option == "Relevance Score ↓":
        filtered = sorted(filtered, key=lambda j: j.relevance_score, reverse=True)
    elif sort_option == "Posted Date ↓":
        filtered = sorted(filtered, key=lambda j: j.posted_date, reverse=True)
    elif sort_option == "Company A-Z":
        filtered = sorted(filtered, key=lambda j: j.company.lower())
    elif sort_option == "Immediate Joining First":
        def joining_rank(j):
            jp = (j.llm_joining_period or "").lower()
            if "immediate" in jp:
                return 0
            elif "notice" in jp:
                return 1
            return 2
        filtered = sorted(filtered, key=joining_rank)

    st.markdown(f"**Showing {len(filtered)} jobs**")

    # Export button
    if st.session_state.csv_filepath and os.path.exists(st.session_state.csv_filepath):
        with open(st.session_state.csv_filepath, "rb") as f:
            st.download_button(
                "📥 Download CSV",
                data=f.read(),
                file_name=os.path.basename(st.session_state.csv_filepath),
                mime="text/csv",
                key="csv_dl",
            )

    def on_applied_change(updated_jobs):
        """Re-export CSV when applied status changes."""
        AppliedStore(st.session_state.applied_store_path).update_from_jobs(updated_jobs)
        if st.session_state.csv_filepath:
            exporter = ExportController()
            exporter.update_applied_status(updated_jobs, st.session_state.csv_filepath)

    render_job_table(filtered, on_applied_change=on_applied_change)

elif st.session_state.search_done and not st.session_state.jobs:
    st.warning("🔍 No jobs matched your criteria. Try relaxing the filters.")
else:
    # Landing page
    st.markdown("""
    ### 🚀 How it works
    1. **Configure** your search in the sidebar — every field is optional
    2. **Hit Hunt Jobs** to scrape Naukri, Foundit, Shine & more — using real browsers that bypass CAPTCHA
    3. **AI analyzes** each job in detail: tech stack breakdown, joining period, location (remote/hybrid/onsite), and relevance score
    4. **Sort & filter** by relevance score, joining period, or source
    5. **Click Apply** links to open jobs in a new tab, check ✅ when done
    6. **Download CSV** with full analysis — share with mentors or track your progress
    
    ---
    
    **🌐 Supported Portals:** Naukri.com · Foundit (Monster India) · Shine.com · AI Multi-Site  
    **🤖 AI Analysis includes:** Relevance Score · Tech Stack Breakdown · Joining Period · Work Mode · Detailed Fit Summary  
    **🧠 Supported LLMs:** Mistral 7B · Llama 3 8B · Gemma 2B · Zephyr 7B · Falcon 7B *(all free via HuggingFace)*
    """)
