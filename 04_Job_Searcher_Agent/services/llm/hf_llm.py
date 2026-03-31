import re
import json
import time
import logging
from huggingface_hub import InferenceClient
from models.job import Job
from models.search_config import SearchConfig
from config.settings import settings
from .base_llm import BaseLLM

logger = logging.getLogger(__name__)


class HuggingFaceLLM(BaseLLM):
    """
    Uses HuggingFace Inference API (free tier) to:
      1. Score job relevance against the user's profile
      2. Generate detailed analysis (tech stack, joining period, location)
    """

    def __init__(self, config: SearchConfig):
        super().__init__(config)
        self.token = config.hf_token
        self.model = config.hf_model
        # Prefer Hugging Face's own inference provider first (more predictable).
        # Keep an auto-router client as a fallback in case a model is only available via a partner provider.
        self.client_hf = InferenceClient(provider="hf-inference", api_key=self.token)
        self.client_auto = InferenceClient(provider="auto", api_key=self.token)

    # ─── Core API call ────────────────────────────────────────────────────────

    def generate_text(self, prompt: str, max_tokens: int = 500) -> str:
        """General text generation method with retry logic."""
        if not self.token:
            return ""
        if not self.model:
            return ""

        for attempt in range(settings.MAX_RETRIES):
            try:
                # Many providers expose chat-only ("conversational") models; try chat first.
                try:
                    msg = [{"role": "user", "content": prompt}]
                    resp = self.client_hf.chat_completion(
                        messages=msg, model=self.model, max_tokens=max_tokens, temperature=0.3
                    )
                    content = ""
                    try:
                        content = resp.choices[0].message.content  # type: ignore[attr-defined]
                    except Exception:
                        # Best-effort fallback for shape differences across versions/providers
                        content = getattr(resp, "generated_text", "") or str(resp)
                    content = (content or "").strip()
                    if content:
                        return content
                except Exception:
                    pass

                # Fallback: classic text-generation models
                text = self.client_hf.text_generation(
                    prompt,
                    model=self.model,
                    max_new_tokens=max_tokens,
                    temperature=0.3,
                    return_full_text=False,
                )
                return (text or "").strip()
            except Exception as e:
                # Fallback path: some models are "summarization" pipeline models (e.g. bart-large-cnn).
                # This will not follow structured "SCORE/TECH_STACK" formats, but returning *something*
                # lets the ensemble keep moving if other drivers succeed; otherwise callers treat empty as failure.
                try:
                    summary = self.client_hf.summarization(prompt, model=self.model)
                    if isinstance(summary, dict):
                        cand = summary.get("summary_text", "")
                    else:
                        cand = getattr(summary, "summary_text", "") or str(summary)
                    cand = (cand or "").strip()
                    if cand:
                        return cand
                except Exception:
                    pass

                # Last resort: let auto-router pick a provider (may support chat-only models).
                try:
                    msg = [{"role": "user", "content": prompt}]
                    resp = self.client_auto.chat_completion(
                        messages=msg, model=self.model, max_tokens=max_tokens, temperature=0.3
                    )
                    content = ""
                    try:
                        content = resp.choices[0].message.content  # type: ignore[attr-defined]
                    except Exception:
                        content = getattr(resp, "generated_text", "") or str(resp)
                    content = (content or "").strip()
                    if content:
                        return content
                except Exception:
                    pass
                try:
                    text = self.client_auto.text_generation(
                        prompt,
                        model=self.model,
                        max_new_tokens=max_tokens,
                        temperature=0.3,
                        return_full_text=False,
                    )
                    text = (text or "").strip()
                    if text:
                        return text
                except Exception:
                    pass

                if attempt < settings.MAX_RETRIES - 1:
                    time.sleep(settings.RETRY_DELAY * (attempt + 1))
                else:
                    logger.error(f"LLM generation failed (model={self.model}): {e}")
                    return ""
        return ""

    # ─── Score & summarize a single job ───────────────────────────────────────

    def score_job(self, job: Job) -> tuple:
        """Score a job posting against the user's profile. Returns (score, summary)."""
        prompt = self._build_score_prompt(job)
        try:
            text = self.generate_text(prompt, max_tokens=150)
            if not text:
                return 0.0, "LLM scoring unavailable"
            return self._parse_score_and_summary(text)
        except Exception as e:
            logger.error(f"LLM scoring failed: {e}")
            return 0.0, "LLM scoring unavailable"

    # ─── Detailed job analysis ────────────────────────────────────────────────

    def analyze_job_detailed(self, job: Job) -> dict:
        """
        Generate a detailed structured analysis of a job posting.

        Returns a dict with keys:
          - tech_stack: str      (required tech stack breakdown)
          - joining_period: str  (immediate / notice period / waiting)
          - location_detail: str (remote / hybrid / onsite — city)
          - detailed_summary: str (multi-line detailed analysis)
          - relevance_score: float
        """
        prompt = self._build_analysis_prompt(job)

        try:
            text = self.generate_text(prompt, max_tokens=400)
            if not text:
                return self._fallback_analysis(job)
            return self._parse_analysis(text, job)
        except Exception as e:
            logger.error(f"LLM analysis failed: {e}")
            return self._fallback_analysis(job)

    # ─── Prompt builders ──────────────────────────────────────────────────────

    def _build_score_prompt(self, job: Job) -> str:
        profile_parts = []
        if getattr(self.config, "candidate_resume_text", ""):
            profile_parts.append(f"Candidate Resume Extract:\n{self.config.candidate_resume_text[:2500]}")
        else:
            if self.config.desired_role:
                profile_parts.append(f"Target Role: {self.config.desired_role}")
            if self.config.tech_stacks:
                profile_parts.append(f"Tech Stack: {', '.join(self.config.tech_stacks)}")
            if self.config.total_experience is not None:
                profile_parts.append(f"Years of Experience: {self.config.total_experience}")
            if self.config.keywords:
                profile_parts.append(f"Job Keywords: {self.config.keywords}")

        profile_text = "\n".join(profile_parts) or "Not specified"
        desc_snippet = job.description[:500] if job.description else "No description available"
        tech_text = ", ".join(job.tech_stack[:10]) if job.tech_stack else "Not listed"

        return f"""<s>[INST] You are a job relevance scoring assistant.

Candidate Profile:
{profile_text}

Job Posting:
- Title: {job.title}
- Company: {job.company}
- Location: {job.location}
- Experience Required: {job.experience}
- Tech Stack: {tech_text}
- Description: {desc_snippet}

CRITICAL INSTRUCTION: If the Job's Experience Required is significantly higher than the Candidate's Experience (e.g. Job requires 8+ years but candidate has 1-2 years), you MUST score it 0.

Score this job's relevance for the candidate on a scale of 0-100 and provide a 1-sentence summary.

Respond ONLY in this exact format:
SCORE: <number>
SUMMARY: <one sentence>
[/INST]"""

    def _build_analysis_prompt(self, job: Job) -> str:
        profile_parts = []
        if getattr(self.config, "candidate_resume_text", ""):
            profile_parts.append(f"Candidate Resume Extract:\n{self.config.candidate_resume_text[:2500]}")
        else:
            if self.config.desired_role:
                profile_parts.append(f"Target Role: {self.config.desired_role}")
            if self.config.tech_stacks:
                profile_parts.append(f"Preferred Stack: {', '.join(self.config.tech_stacks)}")
            if self.config.total_experience is not None:
                profile_parts.append(f"Experience: {self.config.total_experience} yrs")
            if self.config.keywords:
                profile_parts.append(f"Keywords: {self.config.keywords}")

        profile_text = "\n".join(profile_parts) or "Not specified"
        desc_snippet = (job.description or "")[:600]
        tech_text = ", ".join(job.tech_stack[:15]) if job.tech_stack else "Not listed"

        return f"""<s>[INST] You are an expert job market analyst. Analyze this job posting in detail.

Candidate Profile:
{profile_text}

Job Posting:
- Title: {job.title}
- Company: {job.company}
- Location: {job.location}
- Experience: {job.experience}
- Salary: {job.salary or 'Not disclosed'}
- Tech Stack: {tech_text}
- Description: {desc_snippet}

CRITICAL INSTRUCTION: If the Job's Experience requires significantly more years than the Candidate has (e.g. Job needs 9+ years but candidate has 1-2 years), you MUST output a SCORE of 0.

Provide a detailed analysis. Respond ONLY in this exact format (each field on its own line):

SCORE: <0-100 relevance score>
TECH_STACK: <list the key technologies/skills needed, comma-separated>
JOINING: <Immediate Joining / Notice Period Required / Not Specified — infer from description>
LOCATION: <Remote / Hybrid / Onsite — include city/region>
SUMMARY: <2-3 sentence detailed analysis covering: role fit, growth potential, and any red flags>
[/INST]"""

    # ─── Response parsers ─────────────────────────────────────────────────────

    def _parse_score_and_summary(self, text: str) -> tuple:
        score = 0.0
        summary = "Could not parse LLM response"
        score_match = re.search(r"SCORE:\s*(\d+(?:\.\d+)?)", text, re.IGNORECASE)
        summary_match = re.search(r"SUMMARY:\s*(.+)", text, re.IGNORECASE)
        if score_match:
            score = min(100.0, max(0.0, float(score_match.group(1))))
        if summary_match:
            summary = summary_match.group(1).strip()
        return score, summary

    def _parse_analysis(self, text: str, job: Job) -> dict:
        """Parse the structured LLM analysis response."""
        result = self._fallback_analysis(job)

        score_match = re.search(r"SCORE:\s*(\d+(?:\.\d+)?)", text, re.IGNORECASE)
        if score_match:
            result["relevance_score"] = min(100.0, max(0.0, float(score_match.group(1))))

        tech_match = re.search(r"TECH_STACK:\s*(.+?)(?=\n|JOINING:|$)", text, re.IGNORECASE | re.DOTALL)
        if tech_match:
            result["tech_stack"] = tech_match.group(1).strip()

        joining_match = re.search(r"JOINING:\s*(.+?)(?=\n|LOCATION:|$)", text, re.IGNORECASE | re.DOTALL)
        if joining_match:
            result["joining_period"] = joining_match.group(1).strip()

        location_match = re.search(r"LOCATION:\s*(.+?)(?=\n|SUMMARY:|$)", text, re.IGNORECASE | re.DOTALL)
        if location_match:
            result["location_detail"] = location_match.group(1).strip()

        summary_match = re.search(r"SUMMARY:\s*(.+)", text, re.IGNORECASE | re.DOTALL)
        if summary_match:
            result["detailed_summary"] = summary_match.group(1).strip()

        return result

    def _fallback_analysis(self, job: Job) -> dict:
        """Build a baseline analysis from the raw scraped fields when LLM is unavailable."""
        tech = ", ".join(job.tech_stack[:10]) if job.tech_stack else "—"
        loc = job.location or "—"

        # Infer joining type from description keywords
        desc_lower = (job.description or "").lower()
        if any(w in desc_lower for w in ["immediate", "urgently", "asap", "immediate joiner"]):
            joining = "Immediate Joining"
        elif any(w in desc_lower for w in ["notice period", "notice"]):
            joining = "Notice Period Required"
        else:
            joining = "Not Specified"

        # Infer remote/onsite
        if any(w in desc_lower for w in ["remote", "work from home", "wfh"]):
            loc_detail = f"Remote — {loc}"
        elif any(w in desc_lower for w in ["hybrid"]):
            loc_detail = f"Hybrid — {loc}"
        else:
            loc_detail = f"Onsite — {loc}"

        return {
            "relevance_score": 0.0,
            "tech_stack": tech,
            "joining_period": joining,
            "location_detail": loc_detail,
            "detailed_summary": f"{job.title} at {job.company}. {job.experience or 'Experience not specified'}. {'CTC: ' + job.salary if job.salary else 'Salary not disclosed'}.",
        }