from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── App ────────────────────────────────────────────────
    APP_TITLE: str = "Deep Research Agent"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # ── LLM Provider ───────────────────────────────────────
    LLM_PROVIDER: str = "ollama"          # "openai" | "ollama"

    # OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"

    # Ollama
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5-coder:1.5b"

    # ── Database ───────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://postgres:password@localhost:5432/research_db"

    # ── Agent tuning ──────────────────────────────────────
    MAX_SUB_QUERIES: int = 4          # Planner max queries per research
    MAX_SOURCES_PER_QUERY: int = 3    # Researcher max results per query
    MAX_CRITIC_RETRIES: int = 2       # Max extra research rounds
    LLM_TIMEOUT_SECONDS: int = 60
    LLM_TEMPERATURE: float = 0.2

    # ── Web search ────────────────────────────────────────
    SEARCH_REGION: str = "in-en"       # DuckDuckGo region
    SEARCH_MAX_RESULTS: int = 5
    PAGE_FETCH_TIMEOUT: int = 10
    PAGE_MAX_CHARS: int = 4000         # Truncate fetched pages to keep prompts lean


@lru_cache()
def get_settings() -> Settings:
    return Settings()
