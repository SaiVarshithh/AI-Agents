# Deep Research Agent

Multi-agent research pipeline with FastAPI + SSE streaming + Streamlit UI.

## Architecture implemented

- API layer: FastAPI endpoints (`/health`, `/sessions`, `/research`)
- Orchestrator: iterative agent loop with critic-driven retry
- Agents: Planner, Researcher, Summarizer, Critic, Synthesizer
- LLM routing: OpenAI or Ollama through one shared client
- Session persistence: in-memory store (drop-in place for PostgreSQL adapter)
- UI: Streamlit client that streams progress and renders final report

## Run locally

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Configure env:

```bash
cp .env.example .env
```

3. Start API:

```bash
uvicorn app.main:app --reload --port 8000
```
4. Create .streamlit folder inside your repo
- Inside `.streamlit` folder, create `secrets.toml` and add: `api_base = "http://localhost:8000"`

5. Start Streamlit UI:

```bash
streamlit run streamlit_app.py
```

## Notes

- For OpenAI, set `LLM_PROVIDER=openai` and `OPENAI_API_KEY`.
- For Ollama, ensure local daemon is running and model exists.
- Search uses DuckDuckGo public endpoint + page text extraction.
- Current session storage is in-memory; you can replace it with a PostgreSQL-backed implementation in `app/services/session_store.py`.
