import os
from models.search_config import SearchConfig
from services.llm.ensemble_llm import EnsembleLLM
from services.llm.hf_llm import HuggingFaceLLM
from services.llm.ollama_llm import OllamaLLM
from models.job import Job


def main():
    # Minimal smoke: ensure drivers initialize and failures don't crash the pipeline.
    cfg = SearchConfig(
        hf_token=os.getenv("HF_TOKEN", ""),
        hf_model=os.getenv("HF_MODEL", "Qwen/Qwen2.5-1.5B-Instruct"),
        enable_llm_scoring=True,
        desired_role="Software Engineer",
        total_experience=2,
        tech_stacks=["Python", "FastAPI", "PostgreSQL"],
    )

    drivers = []
    if cfg.hf_token:
        # Try a couple HF models (any one may be unavailable)
        for m in [
            "Qwen/Qwen2.5-1.5B-Instruct",
            "facebook/bart-large-cnn",
        ]:
            c = SearchConfig(**{**cfg.__dict__, "hf_model": m})
            drivers.append(HuggingFaceLLM(c))

    # Always include an Ollama fallback if user has it running.
    drivers.append(OllamaLLM(cfg, model="ollama/qwen2.5-coder:1.5b"))

    llm = EnsembleLLM(cfg, drivers)

    job = Job(
        source="test",
        job_id="1",
        title="Python Backend Engineer",
        company="ExampleCo",
        location="Remote",
        experience="2-4 years",
        salary="",
        posted_date="",
        description="We need Python, FastAPI, PostgreSQL. Remote role. Notice period ok.",
        apply_url="",
        tech_stack=["Python", "FastAPI", "PostgreSQL"],
        job_type="",
        industry="",
    )

    analysis = llm.analyze_job_detailed(job)
    assert isinstance(analysis, dict)
    assert "detailed_summary" in analysis
    print("OK: analyze_job_detailed returned without crashing.")


if __name__ == "__main__":
    main()

