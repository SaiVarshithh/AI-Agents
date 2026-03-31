import streamlit as st
from models.search_config import SearchConfig
from config.settings import settings
from services.scrapers.registry import SiteRegistry
import os
from utils.resume_parser import extract_text_from_file


def render_sidebar() -> SearchConfig:
    """Render full sidebar config form and return SearchConfig."""
    st.sidebar.title("⚙️ Job Hunt Config")

    with st.sidebar.expander("🔑 LLM Settings", expanded=False):
        if hf_token_val := st.session_state.get("hf_token_val", ""):
            pass
        hf_token = st.text_input(
            "HuggingFace Token (optional)",
            value=st.session_state.get("hf_token_val", settings.HF_TOKEN or ""),
            type="password",
            help="Get your free token at huggingface.co/settings/tokens — needed for LLM analysis",
            key="hf_token_input",
        )
        st.session_state["hf_token_val"] = hf_token
        hf_model = st.selectbox(
            "LLM Model",
            options=settings.SUPPORTED_MODELS,
            index=0,
            help="Free HuggingFace Inference API models",
        )
        enable_llm = st.checkbox(
            "Enable LLM Analysis & Scoring",
            value=bool(hf_token),
            help="Analyzes each job: tech stack, joining period, location detail, and relevance score.",
        )
        llm_threshold = st.slider(
            "Min Relevance Score Filter",
            min_value=0,
            max_value=100,
            value=0,
            help="Hide jobs below this score (0 = show all)",
        ) if enable_llm else 0

    with st.sidebar.expander("🌐 Job Sources", expanded=True):
        registry = SiteRegistry()
        dynamic_sources = registry.supported_source_names()
        preferred_defaults = [s for s in dynamic_sources if s.lower() not in ("llm", "llm_powered")]
        default_sources = preferred_defaults if preferred_defaults else dynamic_sources
        source_labels = {
            "naukri": "🔵 Naukri.com",
            "monster": "🟠 Foundit (Monster India)",
            "llm": "🤖 AI-Powered Multi-Site",
            "shine": "🟣 Shine.com",
            "indeed": "🟢 Indeed",
        }
        sources = st.multiselect(
            "Portals to Search",
            options=dynamic_sources,
            default=default_sources,
            format_func=lambda s: source_labels.get(s.lower(), s.capitalize()),
        )
        age_label = st.selectbox(
            "Jobs Posted Within",
            options=list(settings.JOB_AGE_OPTIONS.keys()),
            index=2,
        )
        job_age_days = settings.JOB_AGE_OPTIONS[age_label]
        max_results_per_source = st.slider("Max Results Per Source", 10, 50, 25)
        max_results_total = st.slider("Max Results Total (all sources)", 10, 100, 50)

    with st.sidebar.expander("🧭 Browser Session (for protected sites)", expanded=False):
        playwright_enabled = st.checkbox("Enable browser-based scraping (Playwright)", value=True)
        playwright_headless = st.checkbox(
            "Run browser headless",
            value=True,
            help="Turn off to see the browser window (useful for login/CAPTCHA).",
        )
        storage_upload = st.file_uploader(
            "Upload Playwright storage state (JSON)",
            type=["json"],
            help="Exported storage_state.json with cookies/session.",
        )
        storage_state_path = ""
        if storage_upload is not None:
            os.makedirs(settings.OUTPUT_DIR, exist_ok=True)
            storage_state_path = os.path.join(settings.OUTPUT_DIR, "storage_state.json")
            with open(storage_state_path, "wb") as f:
                f.write(storage_upload.getvalue())

    with st.sidebar.expander("🔍 Search Criteria", expanded=True):
        resume_upload = st.file_uploader(
            "Upload Resume (Optional)",
            type=["pdf", "docx"],
            help="Upload your resume to let the AI automatically match your skills, making manual filters less critical."
        )
        candidate_resume_text = ""
        if resume_upload is not None:
            candidate_resume_text = extract_text_from_file(resume_upload, resume_upload.name) or ""

        keywords = st.text_input(
            "Keywords / Job Title",
            placeholder="e.g. Python Developer, FastAPI",
            help="Main job search keywords (Optional if resume is uploaded)",
        )
        desired_role = st.text_input(
            "Your Target Role (for LLM context)",
            placeholder="e.g. Senior Backend Engineer",
        )
        locations_input = st.text_input(
            "Locations (comma-separated)",
            placeholder="e.g. Hyderabad, Bangalore, Remote",
        )
        locations = [loc.strip() for loc in locations_input.split(",") if loc.strip()]

    with st.sidebar.expander("💼 Experience & CTC", expanded=False):
        exp_col1, exp_col2 = st.columns(2)
        with exp_col1:
            exp_min = st.number_input("Min Exp (yrs)", min_value=0, max_value=30, value=0, step=1)
            exp_min = int(exp_min) if exp_min > 0 else None
        with exp_col2:
            exp_max = st.number_input("Max Exp (yrs)", min_value=0, max_value=30, value=0, step=1)
            exp_max = int(exp_max) if exp_max > 0 else None
        total_exp = st.number_input(
            "Your Total Experience (yrs)", min_value=0, max_value=30, value=0, step=1
        )
        total_exp = int(total_exp) if total_exp > 0 else None

        ctc_col1, ctc_col2 = st.columns(2)
        with ctc_col1:
            ctc_min = st.number_input("Min CTC (LPA)", min_value=0.0, value=0.0, step=0.5)
            ctc_min = float(ctc_min) if ctc_min > 0 else None
        with ctc_col2:
            ctc_max = st.number_input("Max CTC (LPA)", min_value=0.0, value=0.0, step=0.5)
            ctc_max = float(ctc_max) if ctc_max > 0 else None

    with st.sidebar.expander("🛠️ Tech Stack & Filters", expanded=False):
        tech_input = st.text_input(
            "Tech Stack (comma-separated)",
            placeholder="e.g. FastAPI, PostgreSQL, Docker",
        )
        tech_stacks = [t.strip() for t in tech_input.split(",") if t.strip()]
        job_type = st.selectbox("Job Type", options=settings.JOB_TYPE_OPTIONS, index=0)
        industry = st.text_input("Industry", placeholder="e.g. Banking, IT Services")

    return SearchConfig(
        keywords=keywords,
        locations=locations,
        experience_min=exp_min,
        experience_max=exp_max,
        ctc_min=ctc_min,
        ctc_max=ctc_max,
        tech_stacks=tech_stacks,
        job_age_days=job_age_days,
        max_results_per_source=max_results_per_source,
        max_results_total=max_results_total,
        sources=sources if sources else dynamic_sources,
        job_type=job_type if job_type != "Any" else None,
        industry=industry if industry else None,
        desired_role=desired_role,
        total_experience=total_exp,
        candidate_resume_text=candidate_resume_text,
        hf_token=hf_token,
        hf_model=hf_model,
        enable_llm_scoring=enable_llm,
        llm_score_threshold=float(llm_threshold),
        playwright_enabled=playwright_enabled,
        playwright_headless=playwright_headless,
        playwright_storage_state_path=storage_state_path,
    )


def render_results_header(job_count: int, source_breakdown: dict):
    """Render a summary header above the job table."""
    st.markdown("---")
    cols = st.columns(max(len(source_breakdown) + 1, 3))
    cols[0].metric("Total Jobs Found", job_count)
    for i, (source, count) in enumerate(source_breakdown.items()):
        if i + 1 < len(cols):
            cols[i + 1].metric(f"{source.capitalize()}", count)


def render_job_table(jobs, on_applied_change=None):
    """Render jobs with view toggle: detailed cards or compact table."""
    if not jobs:
        st.info("No jobs to display.")
        return

    view_mode = st.radio(
        "View",
        ["📋 Detailed Cards", "📊 Compact Table"],
        horizontal=True,
        key="view_mode_radio",
    )

    if view_mode == "📊 Compact Table":
        _render_compact_table(jobs, on_applied_change)
    else:
        _render_detail_cards(jobs, on_applied_change)


# ─── Detailed card view ──────────────────────────────────────────────────────

def _render_detail_cards(jobs, on_applied_change=None):
    """Render each job as a rich card using native Streamlit columns."""
    for i, job in enumerate(jobs):
        score = job.relevance_score
        if score >= 75:
            accent = "#2ECC71"
            score_label = "🟢 Excellent Match"
        elif score >= 50:
            accent = "#F39C12"
            score_label = "🟡 Good Match"
        elif score > 0:
            accent = "#E74C3C"
            score_label = "🔴 Low Match"
        else:
            accent = "#667eea"
            score_label = "⚪ Not Scored"

        source_icon = {
            "naukri": "🔵", "monster": "🟠", "foundit": "🟠",
            "shine": "🟣", "indeed": "🟢", "llm_powered": "🤖",
        }.get(job.source.lower(), "🌐")

        # ─── Card header: title + company + score ────────────────────
        title_col, score_col = st.columns([5, 1])
        with title_col:
            if job.apply_url:
                st.markdown(
                    f'<a href="{job.apply_url}" target="_blank" style="color:#4A90E2; '
                    f'text-decoration:none; font-size:1.1rem; font-weight:700;">'
                    f'{job.title}</a> &nbsp;'
                    f'<span style="color:#888; font-size:0.85rem;">'
                    f'🏢 {job.company} {source_icon} {job.source.capitalize()}</span>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(f"**{job.title}** — 🏢 {job.company} {source_icon} {job.source.capitalize()}")

        with score_col:
            st.markdown(
                f'<span style="background:{accent}; color:white; padding:4px 12px; '
                f'border-radius:16px; font-weight:700; font-size:0.85rem;">'
                f'{int(score)}</span>',
                unsafe_allow_html=True,
            )

        # ─── Detail fields in native columns ─────────────────────────
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.caption("📍 Location")
        c1.write(job.llm_location_detail or job.location or "—")
        c2.caption("🛠️ Tech Stack")
        c2.write(job.llm_tech_stack or (", ".join(job.tech_stack[:5]) if job.tech_stack else "—"))
        c3.caption("⏱️ Joining")
        c3.write(job.llm_joining_period or "—")
        c4.caption("💼 Experience")
        c4.write(job.experience or "—")
        c5.caption("💰 CTC")
        c5.write(job.salary or "Not Disclosed")
        c6.caption("📅 Posted")
        c6.write(job.posted_date or "—")

        # ─── AI Analysis expander ────────────────────────────────────
        detail_col, applied_col = st.columns([8, 1])

        with detail_col:
            summary = job.llm_detailed_summary or job.match_summary
            if summary and summary not in ("LLM scoring unavailable", "Could not parse LLM response"):
                with st.expander(f"💡 AI Analysis — {job.company}", expanded=False):
                    st.markdown(f"**🎯 Relevance:** {int(score)}/100 — _{score_label}_")
                    st.markdown(f"**🛠️ Required Tech:** {job.llm_tech_stack or 'Not specified'}")
                    st.markdown(f"**⏱️ Joining:** {job.llm_joining_period or 'Not specified'}")
                    st.markdown(f"**📍 Work Mode:** {job.llm_location_detail or job.location or 'Not specified'}")
                    st.markdown(f"**📝 Analysis:** {summary}")

        with applied_col:
            applied = st.checkbox(
                "Applied",
                value=job.applied,
                key=f"applied_{job.source}_{job.job_id}_{i}",
            )
            if applied != job.applied:
                job.applied = applied
                if on_applied_change:
                    on_applied_change(jobs)

        st.markdown("<hr style='margin:6px 0; opacity:0.15;'>", unsafe_allow_html=True)


# ─── Compact table view ──────────────────────────────────────────────────────

def _render_compact_table(jobs, on_applied_change=None):
    """Render jobs in a compact table with key info at a glance."""
    header_cols = st.columns([3, 2, 2, 1.5, 1.5, 1.5, 1.5, 1])
    headers = ["Title & Company", "Location", "Tech Stack", "Joining", "Experience", "CTC", "Score", "✅"]
    for col, header in zip(header_cols, headers):
        col.markdown(f"**{header}**")
    st.markdown("---")

    for i, job in enumerate(jobs):
        cols = st.columns([3, 2, 2, 1.5, 1.5, 1.5, 1.5, 1])

        if job.apply_url:
            title_html = (
                f'<a href="{job.apply_url}" target="_blank" '
                f'style="color:#4A90E2;text-decoration:none;font-weight:600;">'
                f'{job.title}</a>'
            )
        else:
            title_html = f"<b>{job.title}</b>"
        cols[0].markdown(
            f"{title_html}<br><small style='color:#888;'>🏢 {job.company} • {job.source.capitalize()}</small>",
            unsafe_allow_html=True,
        )

        cols[1].write(job.llm_location_detail or job.location or "—")

        tech = job.llm_tech_stack or (", ".join(job.tech_stack[:4]) if job.tech_stack else "—")
        if len(str(tech)) > 35:
            tech = str(tech)[:32] + "…"
        cols[2].write(tech)

        cols[3].write(job.llm_joining_period or "—")
        cols[4].write(job.experience or "—")
        cols[5].write(job.salary or "—")

        score = job.relevance_score
        sc = "#2ECC71" if score >= 75 else "#F39C12" if score >= 50 else "#E74C3C"
        cols[6].markdown(
            f'<span style="background:{sc};color:white;padding:2px 8px;'
            f'border-radius:12px;font-size:12px;font-weight:bold;">{int(score)}</span>',
            unsafe_allow_html=True,
        )

        applied = cols[7].checkbox(
            "✅",
            value=job.applied,
            key=f"applied_tbl_{job.source}_{job.job_id}_{i}",
        )
        if applied != job.applied:
            job.applied = applied
            if on_applied_change:
                on_applied_change(jobs)

        st.markdown("<hr style='margin:4px 0;opacity:0.12;'>", unsafe_allow_html=True)