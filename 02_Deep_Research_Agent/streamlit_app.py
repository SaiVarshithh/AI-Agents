from __future__ import annotations

import json

import requests
import streamlit as st

API_BASE = st.secrets.get("api_base", "http://localhost:8000")

st.set_page_config(page_title="Deep Research Agent", layout="wide")
st.title("Deep Research Agent")
st.caption("Multi-agent research with live streaming updates")

question = st.text_area(
    "What should I research?",
    placeholder="Example: Compare top open-source vector databases for RAG in 2026",
    height=120,
)
run = st.button("Run Research", type="primary")

events_container = st.container()
report_container = st.container()

if run and question.strip():
    payload = {"question": question.strip()}
    with st.spinner("Running pipeline..."):
        with requests.post(f"{API_BASE}/research", json=payload, stream=True, timeout=300) as response:
            if response.status_code >= 400:
                st.error(f"API error: {response.status_code} {response.text[:300]}")
            else:
                final_report = ""
                for raw in response.iter_lines(decode_unicode=True):
                    if not raw:
                        continue
                    if raw.startswith("data: "):
                        try:
                            data = json.loads(raw.removeprefix("data: ").strip())
                        except Exception:
                            continue
                        with events_container:
                            role = data.get("role", "system")
                            message = data.get("message", "")
                            st.write(f"**{role}**: {message}")
                        payload = data.get("payload", {})
                        if isinstance(payload, dict) and payload.get("report_markdown"):
                            final_report = payload["report_markdown"]

                with report_container:
                    if final_report:
                        st.markdown("## Final Report")
                        st.markdown(final_report)
                    else:
                        st.info("No final report was returned by the pipeline.")
