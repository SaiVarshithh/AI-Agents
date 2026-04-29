"""
Code Review Agent — Streamlit UI (Rebuilt)
Key fixes:
- Static analysis runs instantly, shown immediately
- LLM streams token-by-token via st.write_stream — never freezes
- Skips LLM on syntax errors
- Multi-file / ZIP project support
- Clean dark UI
"""
import io
import zipfile
import streamlit as st
from code_review_agent import CodeReviewAgent
from tools.syntax_analyzer import SyntaxAnalyzer
from tools.security_checker import SecurityChecker
from tools.quality_checker import QualityChecker
from tools.multi_file_analyzer import MultiFileAnalyzer
from utils.ollama_client import get_available_models, is_ollama_running
from utils.memory import get_history, get_stats, clear_history

# ── Page Config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Code Review Agent",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Styles ─────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
html,body,[class*="css"]{font-family:'Inter',sans-serif;}
.stApp{background:linear-gradient(135deg,#0d0d1a 0%,#1a1a2e 60%,#16213e 100%);color:#e2e8f0;}
section[data-testid="stSidebar"]{background:#0d0d1a;border-right:1px solid #1e2d45;}
.hero{background:linear-gradient(135deg,#6366f1,#8b5cf6,#ec4899);border-radius:16px;padding:2rem 2.5rem;margin-bottom:1.5rem;}
.hero h1{color:#fff;font-size:2rem;font-weight:700;margin:0;}
.hero p{color:rgba(255,255,255,.85);margin:.4rem 0 0;font-size:1rem;}
.card{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.07);border-radius:12px;padding:1.2rem 1.5rem;text-align:center;transition:transform .2s;}
.card:hover{transform:translateY(-3px);}
.card .lbl{font-size:.7rem;color:#64748b;text-transform:uppercase;letter-spacing:.1em;}
.card .val{font-size:1.9rem;font-weight:700;margin-top:4px;}
.step{display:flex;align-items:center;gap:10px;padding:9px 14px;border-radius:9px;margin-bottom:6px;font-size:.88rem;font-weight:500;background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.05);}
.step-running{border-color:#6366f1;background:rgba(99,102,241,.1);animation:pulse 1.4s infinite;}
.step-done{border-color:#22c55e;background:rgba(34,197,94,.08);}
.step-error{border-color:#ef4444;background:rgba(239,68,68,.08);}
.step-pending{opacity:.4;}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.55}}
.badge{display:inline-block;padding:2px 9px;border-radius:20px;font-size:.7rem;font-weight:600;text-transform:uppercase;letter-spacing:.06em;}
.bc{background:rgba(239,68,68,.18);color:#f87171;border:1px solid rgba(239,68,68,.35);}
.bw{background:rgba(245,158,11,.18);color:#fbbf24;border:1px solid rgba(245,158,11,.35);}
.bi{background:rgba(99,102,241,.18);color:#818cf8;border:1px solid rgba(99,102,241,.35);}
.icard{background:rgba(255,255,255,.03);border-left:3px solid #334155;border-radius:0 8px 8px 0;padding:10px 14px;margin-bottom:7px;}
.icard.critical{border-left-color:#ef4444;}.icard.warning{border-left-color:#f59e0b;}.icard.info{border-left-color:#6366f1;}
.imsg{font-size:.85rem;color:#e2e8f0;margin:2px 0;}.ihint{font-size:.78rem;color:#64748b;margin-top:3px;}.iline{font-size:.72rem;color:#475569;font-family:'JetBrains Mono',monospace;}
.ring{width:110px;height:110px;border-radius:50%;display:flex;flex-direction:column;align-items:center;justify-content:center;margin:0 auto 1rem;font-weight:700;}
.gA{background:conic-gradient(#22c55e,#4ade80,#22c55e);box-shadow:0 0 20px rgba(34,197,94,.4);}
.gB{background:conic-gradient(#6366f1,#818cf8,#6366f1);box-shadow:0 0 20px rgba(99,102,241,.4);}
.gC{background:conic-gradient(#f59e0b,#fcd34d,#f59e0b);box-shadow:0 0 20px rgba(245,158,11,.4);}
.gD{background:conic-gradient(#ef4444,#f87171,#ef4444);box-shadow:0 0 20px rgba(239,68,68,.4);}
.gF{background:conic-gradient(#dc2626,#ef4444,#dc2626);box-shadow:0 0 20px rgba(220,38,38,.4);}
.dep-box{background:#0f172a;border:1px solid #1e293b;border-radius:10px;padding:1rem;font-family:'JetBrains Mono',monospace;font-size:.82rem;line-height:1.7;white-space:pre;}
.stTextArea textarea{background:#0d1117!important;color:#e2e8f0!important;font-family:'JetBrains Mono',monospace!important;font-size:.85rem!important;border:1px solid #1e293b!important;border-radius:8px!important;}
.stButton>button{background:linear-gradient(135deg,#6366f1,#8b5cf6)!important;color:#fff!important;border:none!important;border-radius:9px!important;font-weight:600!important;transition:opacity .2s,transform .2s!important;}
.stButton>button:hover{opacity:.85!important;transform:translateY(-1px)!important;}
.stTabs [data-baseweb="tab-list"]{background:rgba(255,255,255,.03)!important;border-radius:10px!important;padding:3px!important;}
.stTabs [data-baseweb="tab"]{background:transparent!important;color:#64748b!important;border-radius:7px!important;font-weight:500!important;}
.stTabs [aria-selected="true"]{background:linear-gradient(135deg,#6366f1,#8b5cf6)!important;color:#fff!important;}
::-webkit-scrollbar{width:5px;height:5px;}::-webkit-scrollbar-track{background:#0d1117;}::-webkit-scrollbar-thumb{background:#334155;border-radius:3px;}
</style>
""", unsafe_allow_html=True)

# ── Constants ──────────────────────────────────────────────────────────────────
SAMPLE = '''import os, pickle, hashlib

SECRET_KEY = "hardcoded_secret_abc123"

class userManager:
    def CreateUser(self, name, age, email, phone, address, dept):
        data = []
        query = "SELECT * FROM users WHERE name = " + name
        result = eval(query)
        return result

    def auth(self, user_data):
        assert user_data is not None
        token = hashlib.md5(str(user_data).encode()).hexdigest()
        return token

def process():
    try:
        with open("data.pkl","rb") as f:
            data = pickle.load(f)
    except:
        pass
    print("Done")
    return data
'''

STEP_ICON = {"running": "⚡", "done": "✅", "error": "❌", "pending": "○"}
STEPS = ["Syntax & Structure", "Security Scan", "Quality Evaluation", "Generating Report"]

def _render_steps(states: dict):
    for step, status in states.items():
        icon = STEP_ICON.get(status, "○")
        cls  = f"step-{status}"
        st.markdown(f'<div class="step {cls}">{icon}&nbsp;&nbsp;{step}</div>', unsafe_allow_html=True)

def _badge(sev):
    cls = {"critical": "bc", "warning": "bw", "info": "bi"}.get(sev, "bi")
    return f'<span class="badge {cls}">{sev}</span>'

def _issue(issue: dict, with_cwe=False):
    sev  = issue.get("severity","info")
    line = f'<div class="iline">Line {issue["line"]}</div>' if issue.get("line") else ""
    cwe  = f'&nbsp;·&nbsp;<code style="font-size:.72rem;color:#475569">{issue.get("cwe","")}</code>' if with_cwe and issue.get("cwe") else ""
    hint = f'<div class="ihint">💡 {issue["suggestion"]}</div>' if issue.get("suggestion") else ""
    title = issue.get("title", issue.get("category","Issue"))
    return f'<div class="icard {sev}">{_badge(sev)}{cwe}<div class="imsg"><b>{title}</b> — {issue.get("message","")}</div>{line}{hint}</div>'

def _metrics(report):
    score_c = {"A":"#22c55e","B":"#6366f1","C":"#f59e0b","D":"#ef4444","F":"#dc2626"}.get(report.quality_grade,"#64748b")
    risk_c  = {"Low":"#22c55e","Medium":"#f59e0b","High":"#ef4444","Critical":"#dc2626"}.get(report.security_risk,"#64748b")
    c1,c2,c3,c4 = st.columns(4)
    for col, lbl, val, color in [
        (c1,"Overall",    report.overall_score,         score_c),
        (c2,"Quality",    f"{report.quality_score}/100",score_c),
        (c3,"Security",   report.security_risk,         risk_c),
        (c4,"Issues",     str(report.total_issues),     "#f87171"),
    ]:
        col.markdown(f'<div class="card"><div class="lbl">{lbl}</div><div class="val" style="color:{color}">{val}</div></div>', unsafe_allow_html=True)

def _issue_tabs(report, show_info):
    t_sec, t_syn, t_qual = st.tabs(["🔒 Security","⚙️ Syntax","✨ Quality"])
    with t_sec:
        issues = [i for i in report.security_issues if show_info or i.get("severity")!="info"]
        if not issues: st.success("✅ No security issues!")
        else:
            for i in issues: st.markdown(_issue(i, with_cwe=True), unsafe_allow_html=True)
    with t_syn:
        m = report.syntax_metrics
        if not report.syntax_valid:
            st.error(f"❌ Syntax Error: `{report.syntax_error}`")
        else:
            st.success("✅ Valid Python")
            if m:
                cols = st.columns(4)
                for col, k, lbl in zip(cols,["total_lines","functions","classes","avg_complexity"],["Lines","Functions","Classes","Avg Complexity"]):
                    col.metric(lbl, m.get(k,0))
        issues = [i for i in report.syntax_issues if show_info or i.get("severity")!="info"]
        for i in issues: st.markdown(_issue(i), unsafe_allow_html=True)
    with t_qual:
        g = report.quality_grade
        st.markdown(f'<div class="ring g{g}"><div style="font-size:2rem;color:#fff">{g}</div><div style="font-size:.75rem;color:rgba(255,255,255,.8)">{report.quality_score}/100</div></div>', unsafe_allow_html=True)
        issues = [i for i in report.quality_issues if show_info or i.get("severity")!="info"]
        if not issues: st.success("✅ Excellent quality!")
        else:
            for i in issues: st.markdown(_issue(i), unsafe_allow_html=True)

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🔍 Code Review Agent")
    st.divider()
    ollama_ok = is_ollama_running()
    if ollama_ok:
        st.markdown('<span style="color:#22c55e;font-weight:600">🟢 Ollama Online</span>', unsafe_allow_html=True)
        models = get_available_models() or ["qwen3:4b"]
        default = "qwen3:4b"
        selected_model = st.selectbox("🤖 Model", models, index=models.index(default) if default in models else 0)
    else:
        st.markdown('<span style="color:#ef4444;font-weight:600">🔴 Ollama Offline</span>', unsafe_allow_html=True)
        st.info("Static analysis still works!\n```\nollama serve\nollama pull qwen3:4b\n```")
        selected_model = "qwen3:4b"
    st.divider()
    stats = get_stats()
    st.markdown("### 📊 Stats")
    c1,c2 = st.columns(2)
    c1.metric("Reviews", stats.get("total_reviews",0))
    c2.metric("Issues Found", stats.get("total_issues_found",0))
    st.divider()
    st.markdown("### ⚙️ Options")
    show_info = st.toggle("Show info-level issues", True)
    st.divider()
    if st.button("🗑️ Clear History"):
        clear_history(); st.success("Cleared!"); st.rerun()
    st.caption("Powered by Ollama · AST · Static Analysis")

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="hero">
  <h1>🔍 Code Review Agent</h1>
  <p>Multi-step AI: instant static analysis → streaming LLM deep-dive · Single file or entire project (ZIP)</p>
</div>
""", unsafe_allow_html=True)

# ── Mode Tabs ──────────────────────────────────────────────────────────────────
mode_single, mode_project = st.tabs(["📄 Single File Review", "📦 Project / Multi-File Review"])

# ══════════════════════════════════════════════════════════════════════════════
# SINGLE FILE MODE
# ══════════════════════════════════════════════════════════════════════════════
with mode_single:
    left, right = st.columns([1,1], gap="large")

    with left:
        st.markdown("### 📝 Your Code")
        tab_paste, tab_upload = st.tabs(["✏️ Paste","📁 Upload .py"])
        code_input = ""
        with tab_paste:
            if st.button("Load Sample (Buggy Code)", key="sample"):
                st.session_state["_sample"] = True
            default = SAMPLE if st.session_state.get("_sample") else ""
            code_input = st.text_area("Code", value=default, height=380,
                                      label_visibility="collapsed",
                                      placeholder="# Paste Python code here…", key="code_area")
        with tab_upload:
            up = st.file_uploader("Upload .py", type=["py","txt"], key="single_up")
            if up:
                code_input = up.read().decode("utf-8","replace")
                st.code(code_input[:1500]+("…" if len(code_input)>1500 else ""), language="python")

        run_btn = st.button("🚀 Run Code Review", use_container_width=True, key="run_single")
        if st.button("Clear", use_container_width=True, key="clear_single"):
            for k in ["_sample","_report"]: st.session_state.pop(k,None)
            st.rerun()

        st.markdown("### 🤖 Agent Pipeline")
        steps_ph = st.empty()
        init_steps = {s:"pending" for s in STEPS}
        if "_report" not in st.session_state:
            with steps_ph.container(): _render_steps(init_steps)

    with right:
        results_ph = st.empty()
        if "_report" not in st.session_state:
            with results_ph.container():
                st.markdown("### 📋 Results")
                st.info("Run a review to see results here.")

    # ── Run ──────────────────────────────────────────────────────────────────
    if run_btn:
        if not code_input.strip():
            st.error("Please paste or upload some code first.")
        else:
            agent = CodeReviewAgent(model=selected_model)
            steps_state = {s:"pending" for s in STEPS}

            def on_step(name, status):
                steps_state[name] = status
                with steps_ph.container(): _render_steps(steps_state)

            # Phase 1: Static (instant)
            report = agent.run_static(
                code_input,
                on_step=lambda s,st_: on_step(
                    {"Syntax & Structure Analysis":"Syntax & Structure",
                     "Security Vulnerability Scan":"Security Scan",
                     "Code Quality Evaluation":"Quality Evaluation",
                     "Generating Report":"Generating Report"}.get(s,s), st_)
            )
            st.session_state["_report"] = report

            # Show static results immediately
            with results_ph.container():
                st.markdown("### 📋 Results")
                _metrics(report)
                st.markdown("<br>", unsafe_allow_html=True)

                b1,b2,b3 = st.columns(3)
                b1.markdown(f'<div style="text-align:center"><span class="badge bc">🔴 Critical: {report.critical_count}</span></div>', unsafe_allow_html=True)
                b2.markdown(f'<div style="text-align:center"><span class="badge bw">🟡 Warning: {report.warning_count}</span></div>', unsafe_allow_html=True)
                b3.markdown(f'<div style="text-align:center"><span class="badge bi">🔵 Info: {report.info_count}</span></div>', unsafe_allow_html=True)

                st.divider()
                _issue_tabs(report, show_info)
                st.divider()

                # Phase 2: Stream LLM (token by token — never freezes)
                st.markdown("### 🧠 AI Deep-Dive Analysis")
                if not report.syntax_valid:
                    st.error(f"⚠️ Fix syntax error first: `{report.syntax_error}`")
                elif not ollama_ok:
                    st.warning("Ollama is offline. Start it to get LLM analysis.")
                else:
                    with st.spinner("Streaming AI analysis…"):
                        full_llm = st.write_stream(agent.stream_analysis(code_input, report))
                    report.llm_analysis = full_llm
                    st.session_state["_report"] = report

                # History
                st.divider()
                st.markdown("### 📜 Review History")
                history = get_history()
                if not history:
                    st.caption("No history yet.")
                else:
                    for entry in history[:5]:
                        s = entry["summary"]
                        ts = entry["timestamp"][:16].replace("T"," ")
                        with st.expander(f"#{entry['id']} · {ts} · {s['overall_score']}"):
                            hc1,hc2,hc3 = st.columns(3)
                            hc1.metric("Issues", s["total_issues"])
                            hc2.metric("Critical", s["critical"])
                            hc3.metric("Score", s["overall_score"])
                            st.code(entry.get("code_preview",""), language="python")


# ══════════════════════════════════════════════════════════════════════════════
# PROJECT / MULTI-FILE MODE
# ══════════════════════════════════════════════════════════════════════════════
with mode_project:
    st.markdown("### 📦 Upload a Python Project")
    st.caption("Upload a `.zip` of your project folder — all `.py` files will be analyzed together with cross-file dependency tracking.")

    zip_up = st.file_uploader("Upload ZIP", type=["zip"], key="zip_up")
    proj_btn = st.button("🔬 Analyze Project", use_container_width=False, key="run_project")

    if zip_up and proj_btn:
        # Extract .py files from ZIP
        files: dict[str,str] = {}
        with zipfile.ZipFile(io.BytesIO(zip_up.read())) as z:
            for name in z.namelist():
                if name.endswith(".py") and not name.startswith("__MACOSX"):
                    try:
                        content = z.read(name).decode("utf-8","replace")
                        short = name.split("/")[-1]  # just filename
                        files[short] = content
                    except Exception:
                        pass

        if not files:
            st.error("No `.py` files found in the ZIP.")
        else:
            syn = SyntaxAnalyzer()
            sec = SecurityChecker()
            qua = QualityChecker()
            mfa = MultiFileAnalyzer(syn, sec, qua)

            prog_ph = st.empty()
            file_list = list(files.keys())
            progress = st.progress(0, text="Analyzing files…")

            def on_prog(fname):
                idx = file_list.index(fname) if fname in file_list else 0
                progress.progress((idx+1)/len(files), text=f"Analyzing {fname}…")

            proj = mfa.analyze_project(files, on_progress=on_prog)
            progress.empty()

            # ── Project Summary ──────────────────────────────────────────────
            st.markdown("---")
            st.markdown("## 🗂️ Project Overview")
            gc = {"A":"#22c55e","B":"#6366f1","C":"#f59e0b","D":"#ef4444","F":"#dc2626"}.get(proj.project_grade,"#64748b")
            p1,p2,p3,p4,p5 = st.columns(5)
            for col, lbl, val, color in [
                (p1,"Files",    proj.total_files,    "#e2e8f0"),
                (p2,"Lines",    proj.total_lines,    "#e2e8f0"),
                (p3,"Issues",   proj.total_issues,   "#f87171"),
                (p4,"Critical", proj.total_critical, "#ef4444"),
                (p5,"Grade",    proj.project_grade,  gc),
            ]:
                col.markdown(f'<div class="card"><div class="lbl">{lbl}</div><div class="val" style="color:{color}">{val}</div></div>', unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)

            # ── Import Graph ──────────────────────────────────────────────────
            st.markdown("### 🔗 Import Dependency Graph")
            if proj.circular_imports:
                st.error(f"⚠️ Circular imports detected: {proj.circular_imports}")
            if proj.entry_points:
                st.info(f"🚀 Entry points: `{'`, `'.join(proj.entry_points)}`")

            dep_lines = []
            for mod, deps in proj.import_graph.items():
                if deps:
                    dep_lines.append(f"  {mod}  →  {', '.join(deps)}")
                else:
                    dep_lines.append(f"  {mod}  (standalone)")
            st.markdown(f'<div class="dep-box">{"<br>".join(dep_lines)}</div>', unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)

            # ── Per-File Breakdown ────────────────────────────────────────────
            st.markdown("### 📄 Per-File Breakdown")
            for fname, fr in proj.files.items():
                risk_emoji = {"Low":"🟢","Medium":"🟡","High":"🔴","Critical":"🔴"}.get(fr.risk_level,"⚪")
                grade_str = f"Q:{fr.quality_score}/100 ({fr.quality_grade})"
                header = f"{'❌' if not fr.syntax_valid else '✅'} **{fname}** — {fr.lines} lines | {fr.functions} fn | {fr.classes} cls | {grade_str} | {risk_emoji} {fr.risk_level}"
                with st.expander(header):
                    if not fr.syntax_valid:
                        st.error(f"Syntax Error: {fr.syntax_error}")
                    col1,col2 = st.columns(2)
                    col1.metric("Issues", fr.issues_count)
                    col2.metric("Critical", fr.critical_count)
                    if fr.internal_imports:
                        st.caption(f"Imports internally: `{'`, `'.join(fr.internal_imports)}`")
                    st.code(files[fname][:800]+("…" if len(files[fname])>800 else ""), language="python")

            st.markdown("---")

            # ── LLM Project Analysis ──────────────────────────────────────────
            st.markdown("### 🧠 AI Project-Level Analysis")
            if not ollama_ok:
                st.warning("Ollama is offline. Start it for AI project analysis.")
            else:
                context = mfa.build_llm_context(files, proj)

                # Create a dummy single-file report for the LLM call
                from code_review_agent import ReviewReport
                dummy = ReviewReport(
                    syntax_valid=True,
                    security_risk=max(
                        (fr.risk_level for fr in proj.files.values()),
                        key=lambda r: ["Low","Medium","High","Critical"].index(r) if r in ["Low","Medium","High","Critical"] else 0,
                        default="Low"
                    ),
                    quality_score=proj.project_score,
                    quality_grade=proj.project_grade,
                    syntax_issues=[],
                    security_issues=[],
                    quality_issues=[],
                )

                agent = CodeReviewAgent(model=selected_model)

                # Use the largest file as "primary code"
                primary = max(files, key=lambda f: len(files[f]))

                with st.spinner("Streaming project AI analysis…"):
                    st.write_stream(agent.stream_analysis(files[primary], dummy, context=context))
