"""
Syntax & Structure Analyzer
Uses Python's AST module to extract structural metrics and detect
common syntax-level issues without executing any code.
"""
import ast
import re
from dataclasses import dataclass, field


@dataclass
class Issue:
    severity: str          # "critical" | "warning" | "info"
    category: str
    message: str
    line: int | None = None
    suggestion: str = ""


@dataclass
class SyntaxReport:
    is_valid_python: bool
    parse_error: str | None
    issues: list[Issue] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


# ─── Complexity helpers ──────────────────────────────────────────────────────

def _count_complexity(node: ast.AST) -> int:
    """Rough cyclomatic complexity (branches)."""
    branch_nodes = (
        ast.If, ast.For, ast.While, ast.ExceptHandler,
        ast.With, ast.Assert, ast.comprehension,
    )
    return sum(1 for n in ast.walk(node) if isinstance(n, branch_nodes))


def _get_function_info(tree: ast.AST) -> list[dict]:
    funcs = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end_line = getattr(node, "end_lineno", node.lineno)
            length = end_line - node.lineno + 1
            has_docstring = (
                isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ) if node.body else False
            funcs.append({
                "name": node.name,
                "line": node.lineno,
                "length": length,
                "args": len(node.args.args),
                "complexity": _count_complexity(node),
                "has_docstring": has_docstring,
                "is_async": isinstance(node, ast.AsyncFunctionDef),
            })
    return funcs


def _get_class_info(tree: ast.AST) -> list[dict]:
    classes = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            has_docstring = (
                isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
            ) if node.body else False
            methods = [n for n in ast.walk(node) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            classes.append({
                "name": node.name,
                "line": node.lineno,
                "methods": len(methods),
                "has_docstring": has_docstring,
                "bases": len(node.bases),
            })
    return classes


# ─── Main Analyzer ───────────────────────────────────────────────────────────

class SyntaxAnalyzer:
    """Analyzes Python code structure using AST."""

    MAX_FUNCTION_LINES = 50
    MAX_FUNCTION_ARGS = 7
    MAX_COMPLEXITY = 10
    MAX_CLASS_METHODS = 20

    def analyze(self, code: str) -> SyntaxReport:
        # 1. Parse
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return SyntaxReport(
                is_valid_python=False,
                parse_error=f"Line {e.lineno}: {e.msg}",
            )

        report = SyntaxReport(is_valid_python=True, parse_error=None)
        lines = code.splitlines()

        # 2. Functions
        funcs = _get_function_info(tree)
        for fn in funcs:
            if fn["length"] > self.MAX_FUNCTION_LINES:
                report.issues.append(Issue(
                    severity="warning",
                    category="Structure",
                    message=f"Function `{fn['name']}` is {fn['length']} lines long (max recommended: {self.MAX_FUNCTION_LINES})",
                    line=fn["line"],
                    suggestion="Break it into smaller, focused functions.",
                ))
            if fn["args"] > self.MAX_FUNCTION_ARGS:
                report.issues.append(Issue(
                    severity="warning",
                    category="Structure",
                    message=f"Function `{fn['name']}` has {fn['args']} parameters (max recommended: {self.MAX_FUNCTION_ARGS})",
                    line=fn["line"],
                    suggestion="Consider using a dataclass or config object to group related arguments.",
                ))
            if fn["complexity"] > self.MAX_COMPLEXITY:
                report.issues.append(Issue(
                    severity="warning",
                    category="Complexity",
                    message=f"Function `{fn['name']}` has high cyclomatic complexity ({fn['complexity']})",
                    line=fn["line"],
                    suggestion="Extract conditional branches into separate helper functions.",
                ))
            if not fn["has_docstring"]:
                report.issues.append(Issue(
                    severity="info",
                    category="Documentation",
                    message=f"Function `{fn['name']}` is missing a docstring",
                    line=fn["line"],
                    suggestion='Add a docstring: """Brief description of what this function does."""',
                ))

        # 3. Classes
        classes = _get_class_info(tree)
        for cls in classes:
            if not cls["has_docstring"]:
                report.issues.append(Issue(
                    severity="info",
                    category="Documentation",
                    message=f"Class `{cls['name']}` is missing a docstring",
                    line=cls["line"],
                    suggestion="Document what this class represents and its responsibilities.",
                ))
            if cls["methods"] > self.MAX_CLASS_METHODS:
                report.issues.append(Issue(
                    severity="warning",
                    category="Structure",
                    message=f"Class `{cls['name']}` has {cls['methods']} methods — may violate Single Responsibility Principle",
                    line=cls["line"],
                    suggestion="Consider splitting into multiple focused classes.",
                ))

        # 4. Bare except
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                report.issues.append(Issue(
                    severity="warning",
                    category="Error Handling",
                    message="Bare `except:` catches all exceptions including SystemExit and KeyboardInterrupt",
                    line=node.lineno,
                    suggestion="Use `except Exception as e:` or catch specific exception types.",
                ))

        # 5. Mutable default arguments
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for default in node.args.defaults:
                    if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                        report.issues.append(Issue(
                            severity="warning",
                            category="Bug Risk",
                            message=f"Function `{node.name}` uses a mutable default argument (list/dict/set)",
                            line=node.lineno,
                            suggestion="Use `None` as default and initialize inside the function body.",
                        ))

        # 6. Long lines
        for i, line in enumerate(lines, 1):
            if len(line) > 120:
                report.issues.append(Issue(
                    severity="info",
                    category="Style",
                    message=f"Line {i} exceeds 120 characters ({len(line)} chars)",
                    line=i,
                    suggestion="Break long lines for readability (PEP 8 recommends ≤ 79 chars).",
                ))

        # 7. Metrics
        imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
        report.metrics = {
            "total_lines": len(lines),
            "blank_lines": sum(1 for l in lines if not l.strip()),
            "comment_lines": sum(1 for l in lines if l.strip().startswith("#")),
            "functions": len(funcs),
            "classes": len(classes),
            "imports": len(imports),
            "async_functions": sum(1 for f in funcs if f["is_async"]),
            "avg_function_length": round(sum(f["length"] for f in funcs) / len(funcs), 1) if funcs else 0,
            "avg_complexity": round(sum(f["complexity"] for f in funcs) / len(funcs), 1) if funcs else 0,
        }

        return report