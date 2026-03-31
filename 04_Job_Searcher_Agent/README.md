# 🎯 Job Hunter AI

A production-grade job scraping + LLM relevance scoring tool with a Streamlit UI.

## Features
- Scrapes **Naukri.com** and **Monster India** (config-driven, extensible)
- Scores job relevance using free **HuggingFace LLMs**
- All search params are optional and configurable
- Apply tracking with checkbox (persisted + auto-updates CSV)
- Export up to 50 jobs per source as CSV

## Setup
```bash
cd job-hunter-ai
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your HF_TOKEN
python -m playwright install chromium
streamlit run app.py
```

## Project Structure (MVC)
```
job-hunter-ai/
├── app.py                    ← Streamlit entry point (View layer)
├── models/                   ← Data models (Job, SearchConfig)
├── controllers/              ← Business logic (search, export)
├── services/
│   ├── scrapers/             ← Config-driven scraper engine
│   └── llm/                  ← HuggingFace LLM scoring
├── views/                    ← Streamlit UI components
├── config/                   ← Settings loader
│   └── sites/                ← Add new sites here (JSON) — no code changes
└── utils/                    ← Helper utilities
```

## Adding a New Job Website (No Code Changes)
1. Create a new JSON file in `config/sites/`, for example `config/sites/myportal.json`
2. Define:
   - `strategy`: `http_json` or `http_json_paged`
   - `request.url`, `request.params`
   - `response.items_path` (JMESPath)
   - `mappings` (JMESPath per field)
   - optional `transforms`
3. Restart Streamlit — the portal automatically appears in the sidebar.

## What you need to provide (so protected sites work)
- **Playwright browser**: run `python -m playwright install chromium` once.
- **Session storage state (recommended)**: a `storage_state.json` exported from Playwright after you log in / solve CAPTCHA in a real browser session for the site.
  - In the app sidebar: upload the JSON under **Browser Session (for protected sites)**.
  - If you don’t provide it, sites like Naukri/Foundit may return “recaptcha required” or HTML instead of JSON.

## Getting a Free HuggingFace Token
1. Go to https://huggingface.co/settings/tokens
2. Create a new token (Read access is enough)
3. Paste it in the sidebar or `.env` file