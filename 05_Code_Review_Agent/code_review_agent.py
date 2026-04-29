"""
Code Review Agent — Main Orchestrator
5-step pipeline:
  Step 1: Syntax & Structure  (AST — instant)
  Step 2: Security Scan       (Pattern + AST — instant)
  Step 3: Quality Evaluation  (AST — instant)
  Step 4: LLM Deep-Dive       (Ollama — streamed, never blocks)
  Step 5: Report Generation   (Aggregated)
"""
from __future__ import annotations
from utils.logger import get_logger

log = get_logger("agent")
import time
from dataclasses import dataclass, field
from typing import Callable, Generator

from tools.syntax_analyzer import SyntaxAnalyzer
from tools.security_checker import SecurityChecker
from tools.quality_checker import QualityChecker
from utils.ollama_client import chat, is_ollama_running
from utils.memory import save_review


@dataclass
class ReviewReport:
    language: str = "python"
    model: str = ""
    duration_seconds: float = 0.0

    syntax_valid: bool = True
    syntax_error: str | None = None
    syntax_issues: list[dict] = field(default_factory=list)
    syntax_metrics: dict = field(default_factory=dict)

    security_issues: list[dict] = field(default_factory=list)
    security_risk: str = "Low"

    quality_issues: list[dict] = field(default_factory=list)
    quality_score: int = 100
    quality_grade: str = "A"

    llm_analysis: str = ""

    total_issues: int = 0
    critical_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    overall_score: str = "N/A"
    review_id: str = ""
    error: str | None = None


SYSTEM_PROMPT = """You are a senior software engineer and code reviewer with 15+ years of Python experience.
Give precise, actionable, line-referenced feedback. Be concise but thorough.
Format with clear markdown sections. Reference specific line numbers where possible."""


def _build_prompt(code: str, syntax_sum: str, sec_sum: str, qual_sum: str, context: str = "") -> str:
    ctx = f"\n## Cross-File Context:\n{context}\n" if context else ""
    return f"""Review this Python code deeply.{ctx}

## Static Analysis (already computed):
- Syntax/Structure: {syntax_sum}
- Security: {sec_sum}
- Quality: {qual_sum}

## Code:
```python
{code[:4000]}{"... [truncated]" if len(code) > 4000 else ""}
```

## Provide:
1. **Overall Assessment** — what does it do, is the approach sound?
2. **Critical Issues** — bugs, logic errors, security holes (cite line numbers)
3. **Key Improvements** — top 3 actionable refactors with before/after snippets
4. **Performance** — any bottlenecks?
5. **Quick Wins** — easy style/naming fixes

Be specific. Reference line numbers. Show code examples."""


class CodeReviewAgent:
    def __init__(self, model: str = "qwen3:4b"):
        self.model = model
        self._syntax = SyntaxAnalyzer()
        self._security = SecurityChecker()
        self._quality = QualityChecker()
        log.info("CodeReviewAgent initialised  model=%s", model)

    # ── Phase 1: Static Analysis (fast, < 1 second) ───────────────────────────
    def run_static(
        self,
        code: str,
        language: str = "python",
        on_step: Callable[[str, str], None] | None = None,
    ) -> ReviewReport:
        """Run all static analysis steps. Returns immediately — no LLM call."""
        def notify(step, status):
            if on_step:
                on_step(step, status)

        start = time.time()
        log.info("─── Starting static analysis  language=%s  lines=%d", language, len(code.splitlines()))
        report = ReviewReport(language=language, model=self.model)

        # Step 1: Syntax
        notify("Syntax & Structure Analysis", "running")
        log.info("[Step 1/4] Syntax & Structure Analysis — start")
        try:
            s = self._syntax.analyze(code)
            report.syntax_valid = s.is_valid_python
            report.syntax_error = s.parse_error
            report.syntax_metrics = s.metrics
            report.syntax_issues = [
                {"severity": i.severity, "category": i.category,
                 "message": i.message, "line": i.line, "suggestion": i.suggestion}
                for i in s.issues
            ]
            if report.syntax_valid:
                log.info("[Step 1/4] Syntax OK — %d issues, %d functions, %d classes",
                         len(report.syntax_issues),
                         report.syntax_metrics.get("functions", 0),
                         report.syntax_metrics.get("classes", 0))
            else:
                log.warning("[Step 1/4] Syntax ERROR — %s", report.syntax_error)
            notify("Syntax & Structure Analysis", "done")
        except Exception as e:
            log.error("[Step 1/4] Syntax analysis raised exception: %s", e)
            report.syntax_error = str(e)
            notify("Syntax & Structure Analysis", "error")

        # Step 2: Security
        notify("Security Vulnerability Scan", "running")
        log.info("[Step 2/4] Security Vulnerability Scan — start")
        try:
            sec = self._security.check(code)
            report.security_risk = sec.risk_level
            report.security_issues = [
                {"severity": i.severity, "cwe": i.cwe, "title": i.title,
                 "message": i.message, "line": i.line, "suggestion": i.suggestion}
                for i in sec.issues
            ]
            log.info("[Step 2/4] Security done — risk=%s  vulnerabilities=%d",
                     report.security_risk, len(report.security_issues))
            notify("Security Vulnerability Scan", "done")
        except Exception as e:
            log.error("[Step 2/4] Security scan raised exception: %s", e)
            notify("Security Vulnerability Scan", "error")

        # Step 3: Quality
        notify("Code Quality Evaluation", "running")
        log.info("[Step 3/4] Code Quality Evaluation — start")
        try:
            q = self._quality.check(code)
            report.quality_score = q.score
            report.quality_grade = q.grade
            report.quality_issues = [
                {"severity": i.severity, "category": i.category,
                 "message": i.message, "line": i.line, "suggestion": i.suggestion}
                for i in q.issues
            ]
            log.info("[Step 3/4] Quality done — score=%d  grade=%s  issues=%d",
                     report.quality_score, report.quality_grade, len(report.quality_issues))
            notify("Code Quality Evaluation", "done")
        except Exception as e:
            log.error("[Step 3/4] Quality check raised exception: %s", e)
            notify("Code Quality Evaluation", "error")

        # Step 4: Aggregate report
        notify("Generating Report", "running")
        log.info("[Step 4/4] Aggregating report…")
        all_issues = report.syntax_issues + report.security_issues + report.quality_issues
        report.total_issues = len(all_issues)
        report.critical_count = sum(1 for i in all_issues if i.get("severity") == "critical")
        report.warning_count  = sum(1 for i in all_issues if i.get("severity") == "warning")
        report.info_count     = sum(1 for i in all_issues if i.get("severity") == "info")

        penalty = report.critical_count * 15 + report.warning_count * 5
        raw = max(0, report.quality_score - penalty)
        report.overall_score = (
            "Excellent" if raw >= 90 else
            "Good"      if raw >= 75 else
            "Fair"      if raw >= 60 else
            "Poor"      if raw >= 40 else
            "Needs Refactor"
        )
        report.duration_seconds = round(time.time() - start, 2)
        log.info(
            "[Step 4/4] Report done — overall=%s  total=%d  critical=%d  warning=%d  info=%d  took=%.2fs",
            report.overall_score, report.total_issues,
            report.critical_count, report.warning_count, report.info_count,
            report.duration_seconds,
        )
        notify("Generating Report", "done")

        try:
            report.review_id = save_review(
                code_snippet=code, language=language,
                report={"total_issues": report.total_issues,
                        "critical_count": report.critical_count,
                        "warning_count": report.warning_count,
                        "overall_score": report.overall_score},
                model_used=self.model,
            )
        except Exception:
            pass

        return report

    # ── Phase 2: Streaming LLM (non-blocking) ────────────────────────────────
    def stream_analysis(
        self,
        code: str,
        report: ReviewReport,
        context: str = "",
    ) -> Generator[str, None, None]:
        """
        Stream LLM tokens one by one — never blocks the UI.
        Skips gracefully if Ollama is offline or code has syntax errors.
        """
        if not report.syntax_valid:
            log.warning("LLM skipped — syntax error: %s", report.syntax_error)
            yield (
                "## ⚠️ Syntax Error Detected\n\n"
                f"```\n{report.syntax_error}\n```\n\n"
                "Fix the syntax error first — the LLM analysis requires valid Python."
            )
            return

        if not is_ollama_running():
            log.warning("LLM skipped — Ollama is not running")
            yield (
                "## ⚠️ Ollama Not Running\n\n"
                "Start Ollama and pull a model:\n"
                "```bash\nollama serve\nollama pull qwen3:4b\n```"
            )
            return

        syntax_sum = (
            f"Valid, {len(report.syntax_issues)} issues, "
            f"{report.syntax_metrics.get('functions', 0)} functions, "
            f"avg complexity {report.syntax_metrics.get('avg_complexity', 0)}"
        )
        sec_sum  = f"Risk: {report.security_risk}, {len(report.security_issues)} vulnerabilities"
        qual_sum = f"Score: {report.quality_score}/100 (Grade {report.quality_grade}), {len(report.quality_issues)} issues"

        prompt = _build_prompt(code, syntax_sum, sec_sum, qual_sum, context)
        log.info("LLM stream starting — model=%s  prompt_chars=%d", self.model, len(prompt))
        token_count = 0
        for token in chat(prompt=prompt, model=self.model, system=SYSTEM_PROMPT,
                          temperature=0.2, stream=True):
            token_count += 1
            if token_count % 50 == 0:
                log.debug("LLM streaming… tokens_so_far=%d", token_count)
            yield token
        log.info("LLM stream complete — total_tokens=%d", token_count)