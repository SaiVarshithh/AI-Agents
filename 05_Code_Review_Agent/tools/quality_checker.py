"""
Code Quality Checker
Evaluates Python code against best practices, PEP 8 guidelines,
naming conventions, and common anti-patterns.
Returns a quality score (0–100) and a letter grade.
"""
import ast
import re
from dataclasses import dataclass, field


@dataclass
class QualityIssue:
    severity: str      # "critical" | "warning" | "info"
    category: str
    message: str
    line: int | None = None
    suggestion: str = ""


@dataclass
class QualityReport:
    issues: list[QualityIssue] = field(default_factory=list)
    score: int = 100
    grade: str = "A"


# ─── Naming Conventions ──────────────────────────────────────────────────────

_SNAKE_CASE = re.compile(r'^[a-z_][a-z0-9_]*$')
_PASCAL_CASE = re.compile(r'^[A-Z][a-zA-Z0-9]*$')
_SCREAMING_SNAKE = re.compile(r'^[A-Z_][A-Z0-9_]*$')
_DUNDER = re.compile(r'^__[a-z]+__$')


def _check_naming(tree: ast.AST) -> list[QualityIssue]:
    issues = []
    for node in ast.walk(tree):
        # Function names: snake_case
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = node.name
            if not (_SNAKE_CASE.match(name) or _DUNDER.match(name)):
                issues.append(QualityIssue(
                    severity="warning",
                    category="Naming",
                    message=f"Function `{name}` does not follow snake_case convention",
                    line=node.lineno,
                    suggestion=f"Rename to `{'_'.join(re.sub(r'([A-Z])', r' 1', name).lower().split()).strip('_')}`",
                ))

        # Class names: PascalCase
        if isinstance(node, ast.ClassDef):
            name = node.name
            if not _PASCAL_CASE.match(name):
                issues.append(QualityIssue(
                    severity="warning",
                    category="Naming",
                    message=f"Class `{name}` does not follow PascalCase convention",
                    line=node.lineno,
                    suggestion="Use PascalCase for class names (e.g., `MyClass`).",
                ))

        # Variable assignments at module level: constants should be SCREAMING_SNAKE
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, (str, int, float)):
                if name.upper() == name and not _SCREAMING_SNAKE.match(name):
                    issues.append(QualityIssue(
                        severity="info",
                        category="Naming",
                        message=f"Module-level constant `{name}` should use SCREAMING_SNAKE_CASE",
                        line=node.lineno,
                        suggestion="Use all-caps with underscores for constants: `MY_CONSTANT = 42`.",
                    ))

    return issues


# ─── Magic Numbers / Strings ─────────────────────────────────────────────────

def _check_magic_numbers(tree: ast.AST) -> list[QualityIssue]:
    """Flag numeric literals that should probably be named constants."""
    issues = []
    allowed_literals = {0, 1, -1, 2, 100}  # commonly acceptable inline values
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            if node.value not in allowed_literals and abs(node.value) > 1:
                # Only flag if inside a function body (not top-level assignments)
                issues.append(QualityIssue(
                    severity="info",
                    category="Maintainability",
                    message=f"Magic number `{node.value}` found — consider naming it as a constant",
                    line=getattr(node, "lineno", None),
                    suggestion=f"Extract to a named constant: `MY_VALUE = {node.value}`.",
                ))
    # Cap magic number issues to avoid noise
    return issues[:5]


# ─── Return Type Hints ───────────────────────────────────────────────────────

def _check_type_hints(tree: ast.AST) -> list[QualityIssue]:
    issues = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Skip private/dunder
            if node.name.startswith("__") and node.name.endswith("__"):
                continue
            missing = []
            if node.returns is None:
                missing.append("return type")
            unannotated_args = [
                a.arg for a in node.args.args
                if a.annotation is None and a.arg != "self" and a.arg != "cls"
            ]
            if unannotated_args:
                missing.append(f"arg types ({', '.join(unannotated_args)})")
            if missing:
                issues.append(QualityIssue(
                    severity="info",
                    category="Type Hints",
                    message=f"Function `{node.name}` is missing type annotations: {', '.join(missing)}",
                    line=node.lineno,
                    suggestion="Add type hints for better IDE support and static analysis.",
                ))
    return issues


# ─── Anti-Patterns ───────────────────────────────────────────────────────────

def _check_antipatterns(tree: ast.AST, lines: list[str]) -> list[QualityIssue]:
    issues = []

    for node in ast.walk(tree):
        # isinstance(x, type) == True  →  redundant
        if isinstance(node, ast.Compare):
            for op, comp in zip(node.ops, node.comparators):
                if isinstance(op, (ast.Is, ast.Eq)) and isinstance(comp, ast.Constant):
                    if comp.value is True or comp.value is False:
                        issues.append(QualityIssue(
                            severity="info",
                            category="Anti-Pattern",
                            message="Comparing to True/False with == or is — use the value directly",
                            line=node.lineno,
                            suggestion="Use `if condition:` instead of `if condition == True:`",
                        ))

        # `global` statement usage
        if isinstance(node, ast.Global):
            issues.append(QualityIssue(
                severity="warning",
                category="Anti-Pattern",
                message=f"Use of `global` statement for: {', '.join(node.names)}",
                line=node.lineno,
                suggestion="Avoid global state. Use function parameters, return values, or class attributes.",
            ))

        # `print()` in non-main code (heuristic — flag as info)
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "print":
                issues.append(QualityIssue(
                    severity="info",
                    category="Best Practice",
                    message="Raw `print()` call found — consider using the `logging` module",
                    line=getattr(func, "lineno", None),
                    suggestion="Replace with `logging.info(...)` or `logging.debug(...)` for production code.",
                ))

    # Cap print detections to 3
    print_issues = [i for i in issues if "print()" in i.message]
    non_print = [i for i in issues if "print()" not in i.message]
    return non_print + print_issues[:3]


# ─── Line Quality ────────────────────────────────────────────────────────────

def _check_line_quality(lines: list[str]) -> list[QualityIssue]:
    issues = []
    trailing_blank_count = 0
    for i, line in enumerate(reversed(lines), 1):
        if line.strip() == "":
            trailing_blank_count += 1
        else:
            break

    if trailing_blank_count > 1:
        issues.append(QualityIssue(
            severity="info",
            category="Style",
            message=f"File ends with {trailing_blank_count} trailing blank lines",
            suggestion="PEP 8: files should end with exactly one newline.",
        ))

    # Trailing whitespace
    trailing_ws = [i + 1 for i, l in enumerate(lines) if l != l.rstrip() and l.strip()]
    if trailing_ws:
        sample = trailing_ws[:3]
        issues.append(QualityIssue(
            severity="info",
            category="Style",
            message=f"Trailing whitespace on lines: {sample}{' ...' if len(trailing_ws) > 3 else ''}",
            suggestion="Remove trailing whitespace (most editors can do this automatically).",
        ))

    # Mixed indentation
    has_tabs = any("\t" in l for l in lines)
    has_spaces = any(l.startswith("    ") for l in lines)
    if has_tabs and has_spaces:
        issues.append(QualityIssue(
            severity="warning",
            category="Style",
            message="Mixed tabs and spaces detected for indentation",
            suggestion="Use spaces only (4 spaces per indent level) as per PEP 8.",
        ))

    return issues


# ─── Import Quality ──────────────────────────────────────────────────────────

def _check_imports(tree: ast.AST) -> list[QualityIssue]:
    issues = []
    wildcard_imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    wildcard_imports.append(node.module or "unknown")

    if wildcard_imports:
        issues.append(QualityIssue(
            severity="warning",
            category="Imports",
            message=f"Wildcard import(s) detected: from {', '.join(wildcard_imports)} import *",
            suggestion="Import only what you need. Wildcard imports pollute the namespace and make code harder to read.",
        ))

    return issues


# ─── Scorer ──────────────────────────────────────────────────────────────────

def _compute_score(issues: list[QualityIssue]) -> tuple[int, str]:
    score = 100
    for issue in issues:
        if issue.severity == "critical":
            score -= 20
        elif issue.severity == "warning":
            score -= 8
        elif issue.severity == "info":
            score -= 3
    score = max(0, score)

    if score >= 90:
        grade = "A"
    elif score >= 80:
        grade = "B"
    elif score >= 70:
        grade = "C"
    elif score >= 55:
        grade = "D"
    else:
        grade = "F"

    return score, grade


# ─── Main Checker ────────────────────────────────────────────────────────────

class QualityChecker:
    """Evaluates code quality against Python best practices."""

    def check(self, code: str) -> QualityReport:
        report = QualityReport()
        lines = code.splitlines()

        # Try AST-based checks
        try:
            tree = ast.parse(code)
            report.issues.extend(_check_naming(tree))
            report.issues.extend(_check_type_hints(tree))
            report.issues.extend(_check_antipatterns(tree, lines))
            report.issues.extend(_check_imports(tree))
        except SyntaxError:
            report.issues.append(QualityIssue(
                severity="critical",
                category="Syntax",
                message="Cannot perform quality checks: code has syntax errors",
                suggestion="Fix syntax errors first (see Syntax Analysis tab).",
            ))

        # Line-level checks (always run)
        report.issues.extend(_check_line_quality(lines))

        report.score, report.grade = _compute_score(report.issues)
        return report
