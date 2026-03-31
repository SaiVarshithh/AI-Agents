import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """
    Central config loader. Values can come from:
      1. .env file (via python-dotenv)
      2. Environment variables
      3. Streamlit session state (passed at runtime)
    """

    # HuggingFace
    HF_TOKEN: str = os.getenv("HF_TOKEN", "")
    HF_MODEL: str = os.getenv("HF_MODEL", "mistralai/Mistral-7B-Instruct-v0.3")

    # Scraper defaults
    REQUEST_TIMEOUT: int = int(os.getenv("REQUEST_TIMEOUT", "20"))
    MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))
    RETRY_DELAY: float = float(os.getenv("RETRY_DELAY", "2.0"))

    # CSV output directory
    OUTPUT_DIR: str = os.getenv("OUTPUT_DIR", "output")

    # Dynamic site config directory
    SITES_DIR: str = os.getenv("SITES_DIR", os.path.join("config", "sites"))

    # Supported models
    SUPPORTED_MODELS: list = [
        # Keep only the proven-working set (fast + reliable fallbacks).
        "facebook/bart-large-cnn",
        "mistralai/Mistral-7B-Instruct-v0.3",
        "google/flan-t5-base",
        "ollama/qwen2.5-coder:1.5b",
    ]

    # Job age options (days)
    JOB_AGE_OPTIONS: dict = {
        "Last 24 hours": 1,
        "Last 3 days": 3,
        "Last 7 days": 7,
        "Last 15 days": 15,
        "Last 30 days": 30,
    }

    # Job type options
    JOB_TYPE_OPTIONS: list = [
        "Any",
        "Full Time",
        "Part Time",
        "Contract",
        "Internship",
        "Freelance",
    ]

    # Naukri scraper headers (mimics browser)
    NAUKRI_HEADERS: dict = {
        "Appid": "109",
        "appid": "109",
        "systemid": "jobsearchDesk",
        "SystemId": "jobsearchDesk",
        "systemcountrycode": "IN",
        "gid": "LOCATION,INDUSTRY,EDUCATION,FAREA_ROLE",
        "Content-Type": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.naukri.com/",
    }

    # Monster India scraper headers
    MONSTER_HEADERS: dict = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.foundit.in/",
        "Origin": "https://www.foundit.in",
    }


settings = Settings()
