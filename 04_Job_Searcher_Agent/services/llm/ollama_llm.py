import re
import json
import logging
import requests
from models.job import Job
from models.search_config import SearchConfig
from .base_llm import BaseLLM

logger = logging.getLogger(__name__)

class OllamaLLM(BaseLLM):
    """
    Uses local Ollama API to score jobs and generate detailed analysis.
    Assumes standard localhost:11434 endpoint.
    """

    OLLAMA_API_URL = "http://localhost:11434/api/generate"

    def __init__(self, config: SearchConfig, model: str):
        super().__init__(config)
        self.model = model.replace("ollama/", "")

    def generate_text(self, prompt: str, max_tokens: int = 500) -> str:
        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "num_predict": max_tokens,
                    "temperature": 0.3
                }
            }
            response = requests.post(self.OLLAMA_API_URL, json=payload, timeout=60)
            response.raise_for_status()
            result = response.json()
            return result.get("response", "")
        except Exception as e:
            logger.error(f"Ollama text generation failed: {e}")
            return ""

    def score_job(self, job: Job) -> tuple:
        from services.llm.hf_llm import HuggingFaceLLM
        # We can reuse the prompt builder logic since it's identical
        dummy = HuggingFaceLLM.__new__(HuggingFaceLLM)
        dummy.config = self.config
        prompt = dummy._build_score_prompt(job)
        
        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "num_predict": 150,
                    "temperature": 0.3
                }
            }
            response = requests.post(self.OLLAMA_API_URL, json=payload, timeout=60)
            response.raise_for_status()
            text = response.json().get("response", "")
            return dummy._parse_score_and_summary(text)
        except Exception as e:
            logger.error(f"Ollama scoring failed: {e}")
            return 0.0, "Ollama API unavailable or model not found"

    def analyze_job_detailed(self, job: Job) -> dict:
        from services.llm.hf_llm import HuggingFaceLLM
        dummy = HuggingFaceLLM.__new__(HuggingFaceLLM)
        dummy.config = self.config
        prompt = dummy._build_analysis_prompt(job)

        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "num_predict": 400,
                    "temperature": 0.3
                }
            }
            response = requests.post(self.OLLAMA_API_URL, json=payload, timeout=90)
            response.raise_for_status()
            text = response.json().get("response", "")
            return dummy._parse_analysis(text, job)
        except Exception as e:
            logger.error(f"Ollama analysis failed: {e}")
            return dummy._fallback_analysis(job)
