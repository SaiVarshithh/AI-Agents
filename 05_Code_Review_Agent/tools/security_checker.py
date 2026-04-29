"""
Security Vulnerability Scanner
Pattern-based detection of common Python security issues.
Covers OWASP Top 10 relevant patterns for Python code.
"""
import re
import ast
from dataclasses import dataclass, field


@dataclass
class SecurityIssue:
    severity: str      # "critical" | "warning" | "info"
    cwe: str           # CWE identifier e.g. "CWE-78"
    title: str
    message: str
    line: int | None = None
    suggestion: str = ""


@dataclass
class SecurityReport:
    issues: list[SecurityIssue] = field(default_factory=list)
    risk_level: str = "Low"   # Low | Medium | High | Critical


# ─── Pattern Rules ───────────────────────────────────────────────────────────

LINE_PATTERNS = [
    {
        "pattern": re.compile(r'\beval\s*\(', re.IGNORECASE),
        "severity": "critical",
        "cwe": "CWE-95",
        "title": "Code Injection via eval()",
        "message": "`eval()` executes arbitrary code — extremely dangerous with untrusted input.",
        "suggestion": "Replace with `ast.literal_eval()` for safe literal parsing, or redesign to avoid dynamic execution.",
    },
    {
        "pattern": re.compile(r'\bexec\s*\(', re.IGNORECASE),
        "severity": "critical",
        "cwe": "CWE-78",
        "title": "Code Injection via exec()",
        "message": "`exec()` runs arbitrary Python code — high injection risk.",
        "suggestion": "Avoid exec() with user-controlled data. Redesign using safer abstractions.",
    },
    {
        "pattern": re.compile(r'subprocess\.(call|run|Popen|check_output)\s*\(.*shell\s*=\s*True', re.IGNORECASE),
        "severity": "critical",
        "cwe": "CWE-78",
        "title": "Shell Injection Risk",
        "message": "Using `shell=True` with subprocess allows OS command injection.",
        "suggestion": "Pass commands as a list (e.g., `['ls', '-la']`) and set `shell=False`.",
    },
    {
        "pattern": re.compile(r'os\.system\s*\(', re.IGNORECASE),
        "severity": "critical",
        "cwe": "CWE-78",
        "title": "OS Command Injection",
        "message": "`os.system()` passes commands to the shell — vulnerable to injection.",
        "suggestion": "Use `subprocess.run(['cmd', 'arg'], shell=False)` instead.",
    },
    {
        "pattern": re.compile(
            r'(password|passwd|secret|api_key|token|private_key)\s*=\s*["\'][^"\']{6,}["\']',
            re.IGNORECASE
        ),
        "severity": "critical",
        "cwe": "CWE-798",
        "title": "Hardcoded Secret / Credential",
        "message": "A hardcoded secret, password, or API key was detected.",
        "suggestion": "Load secrets from environment variables: `os.getenv('API_KEY')` or use python-dotenv.",
    },
    {
        "pattern": re.compile(r'pickle\.(loads?|load)\s*\(', re.IGNORECASE),
        "severity": "critical",
        "cwe": "CWE-502",
        "title": "Insecure Deserialization (pickle)",
        "message": "`pickle.load/loads` on untrusted data can execute arbitrary code.",
        "suggestion": "Use `json` or `msgpack` for serialization. Never unpickle data from untrusted sources.",
    },
    {
        "pattern": re.compile(r'yaml\.load\s*\((?!.*Loader)', re.IGNORECASE),
        "severity": "critical",
        "cwe": "CWE-502",
        "title": "Unsafe YAML Load",
        "message": "`yaml.load()` without a Loader argument is dangerous — use `yaml.safe_load()`.",
        "suggestion": "Replace with `yaml.safe_load(data)` or `yaml.load(data, Loader=yaml.SafeLoader)`.",
    },
    {
        "pattern": re.compile(r'verify\s*=\s*False', re.IGNORECASE),
        "severity": "warning",
        "cwe": "CWE-295",
        "title": "TLS Certificate Verification Disabled",
        "message": "`verify=False` disables SSL/TLS certificate verification — MITM attack risk.",
        "suggestion": "Remove `verify=False` or provide the CA bundle path: `verify='/path/to/ca-bundle.crt'`.",
    },
    {
        "pattern": re.compile(r'(SELECT|INSERT|UPDATE|DELETE)\s+.*\+\s*(str|f["\']|format)', re.IGNORECASE),
        "severity": "critical",
        "cwe": "CWE-89",
        "title": "Potential SQL Injection",
        "message": "SQL query appears to be constructed via string concatenation or f-string.",
        "suggestion": "Use parameterized queries: `cursor.execute('SELECT * FROM t WHERE id = %s', (user_id,))`.",
    },
    {
        "pattern": re.compile(r'random\.(random|randint|choice|shuffle)\s*\(', re.IGNORECASE),
        "severity": "info",
        "cwe": "CWE-338",
        "title": "Weak PRNG for Possible Security Use",
        "message": "`random` module uses a non-cryptographic PRNG. Don't use for security-sensitive values.",
        "suggestion": "Use `secrets` module for tokens/passwords: `secrets.token_hex(32)`.",
    },
    {
        "pattern": re.compile(r'hashlib\.(md5|sha1)\s*\(', re.IGNORECASE),
        "severity": "warning",
        "cwe": "CWE-327",
        "title": "Weak Hashing Algorithm",
        "message": "MD5 and SHA-1 are cryptographically broken for security purposes.",
        "suggestion": "Use SHA-256+ for integrity, or `bcrypt`/`argon2` for passwords.",
    },
    {
        "pattern": re.compile(r'DEBUG\s*=\s*True', re.IGNORECASE),
        "severity": "warning",
        "cwe": "CWE-215",
        "title": "Debug Mode Enabled",
        "message": "DEBUG=True can expose stack traces and sensitive info in production.",
        "suggestion": "Set DEBUG=False in production and load via environment variable.",
    },
    {
        "pattern": re.compile(r'open\s*\(.*["\']w["\'].*\).*#.*no.*sanitiz', re.IGNORECASE),
        "severity": "info",
        "cwe": "CWE-73",
        "title": "Potential Path Traversal",
        "message": "File write using potentially unsanitized path.",
        "suggestion": "Validate and sanitize file paths. Use `pathlib.Path.resolve()` and check against allowed directories.",
    },
    {
        "pattern": re.compile(r'input\s*\(', re.IGNORECASE),
        "severity": "info",
        "cwe": "CWE-20",
        "title": "Unvalidated User Input",
        "message": "`input()` reads raw user input — ensure it is validated before use.",
        "suggestion": "Always validate and sanitize input: check type, length, and allowable characters.",
    },
]


# ─── AST-based checks ────────────────────────────────────────────────────────

def _check_assert_used_for_auth(tree: ast.AST) -> list[SecurityIssue]:
    """assert statements can be disabled with -O flag."""
    issues = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            issues.append(SecurityIssue(
                severity="warning",
                cwe="CWE-617",
                title="assert Used for Security Check",
                message="`assert` can be disabled at runtime with `python -O`. Don't use for auth/validation.",
                line=node.lineno,
                suggestion="Replace with explicit `if not condition: raise ValueError(...)` checks.",
            ))
    return issues


def _check_try_pass(tree: ast.AST) -> list[SecurityIssue]:
    """Silently swallowing exceptions hides errors."""
    issues = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                issues.append(SecurityIssue(
                    severity="warning",
                    cwe="CWE-390",
                    title="Exception Silently Swallowed",
                    message="Empty `except: pass` silently hides errors — dangerous in production.",
                    line=node.lineno,
                    suggestion="At minimum, log the exception: `logger.exception(e)` before passing.",
                ))
    return issues


# ─── Risk Scorer ─────────────────────────────────────────────────────────────

def _calculate_risk(issues: list[SecurityIssue]) -> str:
    critical = sum(1 for i in issues if i.severity == "critical")
    warnings = sum(1 for i in issues if i.severity == "warning")
    if critical >= 1:
        return "Critical"
    if warnings >= 3:
        return "High"
    if warnings >= 1:
        return "Medium"
    return "Low"


# ─── Main Checker ────────────────────────────────────────────────────────────

class SecurityChecker:
    """Scans code for known security vulnerabilities."""

    def check(self, code: str) -> SecurityReport:
        report = SecurityReport()
        lines = code.splitlines()

        # Line-level pattern checks
        for line_no, line in enumerate(lines, 1):
            for rule in LINE_PATTERNS:
                if rule["pattern"].search(line):
                    report.issues.append(SecurityIssue(
                        severity=rule["severity"],
                        cwe=rule["cwe"],
                        title=rule["title"],
                        message=rule["message"],
                        line=line_no,
                        suggestion=rule["suggestion"],
                    ))

        # AST-based checks (only if valid Python)
        try:
            tree = ast.parse(code)
            report.issues.extend(_check_assert_used_for_auth(tree))
            report.issues.extend(_check_try_pass(tree))
        except SyntaxError:
            pass  # Syntax issues handled by SyntaxAnalyzer

        # Deduplicate by (line, cwe)
        seen = set()
        unique_issues = []
        for issue in report.issues:
            key = (issue.line, issue.cwe)
            if key not in seen:
                seen.add(key)
                unique_issues.append(issue)
        report.issues = unique_issues

        report.risk_level = _calculate_risk(report.issues)
        return report