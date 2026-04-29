"""
Multi-File Project Analyzer
Analyzes a set of Python files as a project:
- Per-file static analysis
- Import dependency graph
- Circular import detection
- Entry point identification
- Aggregate project health score
"""
from __future__ import annotations
import ast
from dataclasses import dataclass, field
from pathlib import Path
from utils.logger import get_logger

log = get_logger("multi-file")


@dataclass
class FileReport:
    filename: str
    lines: int = 0
    syntax_valid: bool = True
    syntax_error: str | None = None
    functions: int = 0
    classes: int = 0
    imports: list[str] = field(default_factory=list)
    internal_imports: list[str] = field(default_factory=list)
    issues_count: int = 0
    critical_count: int = 0
    risk_level: str = "Low"
    quality_score: int = 100
    quality_grade: str = "A"


@dataclass
class ProjectReport:
    files: dict[str, FileReport] = field(default_factory=dict)
    import_graph: dict[str, list[str]] = field(default_factory=dict)
    circular_imports: list[list[str]] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)
    orphan_files: list[str] = field(default_factory=list)
    total_files: int = 0
    total_lines: int = 0
    total_issues: int = 0
    total_critical: int = 0
    project_score: int = 100
    project_grade: str = "A"


class MultiFileAnalyzer:
    def __init__(self, syntax_analyzer, security_checker, quality_checker):
        self._syntax = syntax_analyzer
        self._security = security_checker
        self._quality = quality_checker

    def analyze_project(
        self,
        files: dict[str, str],
        on_progress: callable | None = None,
    ) -> ProjectReport:
        """Analyze all files and build the project report."""
        log.info("Project analysis started — files=%d", len(files))
        project = ProjectReport(total_files=len(files))
        module_names = {Path(f).stem for f in files}

        for filename, code in files.items():
            if on_progress:
                on_progress(filename)
            log.info("Analyzing file: %s  (%d lines)", filename, len(code.splitlines()))

            fr = FileReport(filename=filename, lines=len(code.splitlines()))
            project.total_lines += fr.lines

            # Syntax
            s = self._syntax.analyze(code)
            fr.syntax_valid = s.is_valid_python
            fr.syntax_error = s.parse_error
            fr.functions = s.metrics.get("functions", 0)
            fr.classes = s.metrics.get("classes", 0)
            fr.issues_count += len(s.issues)

            # Imports (only if parseable)
            if fr.syntax_valid:
                try:
                    tree = ast.parse(code)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import):
                            for alias in node.names:
                                root = alias.name.split(".")[0]
                                fr.imports.append(root)
                                if root in module_names:
                                    fr.internal_imports.append(root)
                        elif isinstance(node, ast.ImportFrom):
                            if node.module:
                                root = node.module.split(".")[0]
                                fr.imports.append(root)
                                if root in module_names:
                                    fr.internal_imports.append(root)
                except Exception:
                    pass

            # Security
            sec = self._security.check(code)
            fr.risk_level = sec.risk_level
            fr.critical_count = sum(1 for i in sec.issues if i.severity == "critical")
            fr.issues_count += len(sec.issues)

            # Quality
            q = self._quality.check(code)
            fr.quality_score = q.score
            fr.quality_grade = q.grade
            fr.issues_count += len(q.issues)

            project.total_issues += fr.issues_count
            project.total_critical += fr.critical_count
            project.files[filename] = fr
            log.info(
                "  └─ %s — syntax=%s  risk=%s  quality=%d  issues=%d",
                filename, "OK" if fr.syntax_valid else "ERROR",
                fr.risk_level, fr.quality_score, fr.issues_count,
            )

            mod = Path(filename).stem
            project.import_graph[mod] = list(set(fr.internal_imports))

        # Entry points: not imported by anyone
        all_imported = {dep for deps in project.import_graph.values() for dep in deps}
        project.entry_points = [m for m in project.import_graph if m not in all_imported]

        # Orphans: no internal imports AND not imported
        project.orphan_files = [
            m for m in project.import_graph
            if not project.import_graph[m] and m not in all_imported
        ]

        # Circular imports
        project.circular_imports = self._find_cycles(project.import_graph)

        # Project score
        avg_quality = (
            sum(fr.quality_score for fr in project.files.values()) / len(project.files)
            if project.files else 100
        )
        penalty = project.total_critical * 10 + len(project.circular_imports) * 15
        raw = max(0, int(avg_quality) - penalty)
        project.project_score = raw
        project.project_grade = (
            "A" if raw >= 90 else "B" if raw >= 80 else
            "C" if raw >= 70 else "D" if raw >= 55 else "F"
        )

        log.info(
            "Project analysis complete — files=%d  lines=%d  issues=%d  critical=%d  grade=%s  cycles=%d",
            project.total_files, project.total_lines, project.total_issues,
            project.total_critical, project.project_grade, len(project.circular_imports),
        )
        if project.circular_imports:
            log.warning("Circular imports detected: %s", project.circular_imports)
        if project.entry_points:
            log.info("Entry points: %s", project.entry_points)

        return project

    def _find_cycles(self, graph: dict[str, list[str]]) -> list[list[str]]:
        """DFS cycle detection."""
        cycles, visited, rec_stack = [], set(), set()

        def dfs(node, path):
            visited.add(node)
            rec_stack.add(node)
            for nb in graph.get(node, []):
                if nb not in visited:
                    dfs(nb, path + [nb])
                elif nb in rec_stack and nb in path:
                    cycle = path[path.index(nb):] + [nb]
                    if cycle not in cycles:
                        cycles.append(cycle)
            rec_stack.discard(node)

        for node in graph:
            if node not in visited:
                dfs(node, [node])
        return cycles[:10]

    def build_llm_context(self, files: dict[str, str], project: ProjectReport, max_chars: int = 5000) -> str:
        """Build condensed multi-file context for LLM prompt."""
        lines = [
            f"## Project: {project.total_files} files, {project.total_lines} lines, "
            f"{project.total_issues} issues, {project.total_critical} critical",
        ]
        if project.entry_points:
            lines.append(f"- Entry points: {', '.join(project.entry_points)}")
        if project.circular_imports:
            lines.append(f"- ⚠️ Circular imports detected: {project.circular_imports}")

        lines.append("\n## Import Dependency Graph")
        for mod, deps in project.import_graph.items():
            arrow = f"  {mod} → {', '.join(deps)}" if deps else f"  {mod} (standalone)"
            lines.append(arrow)

        lines.append("\n## Per-File Summary")
        for fname, fr in project.files.items():
            status = "❌ SYNTAX ERROR" if not fr.syntax_valid else f"✅ Q:{fr.quality_score}/100 | Sec:{fr.risk_level}"
            lines.append(f"  {fname}: {fr.lines}L | {fr.functions}fn | {fr.classes}cls | {status}")

        # Append code snippets until budget runs out
        budget = max_chars - sum(len(l) for l in lines)
        lines.append("\n## Code (truncated per file)")
        for fname, code in files.items():
            if budget < 300:
                lines.append(f"\n[{fname}: omitted — budget exhausted]")
                continue
            take = min(len(code), budget - 60)
            snippet = code[:take] + ("\n... [truncated]" if len(code) > take else "")
            lines.append(f"\n### {fname}\n```python\n{snippet}\n```")
            budget -= take + 60

        return "\n".join(lines)
