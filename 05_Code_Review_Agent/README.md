# 🔍 Code Review Agent

> **AI-Agents Challenge — Day 05**  
> A production-quality, multi-step agentic code reviewer powered by Ollama + AST static analysis.

---

## 🧠 What It Does

The Code Review Agent performs a **5-step agentic pipeline** on your Python code:

| Step | Tool | Description |
|------|------|-------------|
| 1 | `SyntaxAnalyzer` (AST) | Detects syntax errors, complexity, function size issues |
| 2 | `SecurityChecker` (AST + Regex) | Scans for OWASP Top-10 vulnerabilities (eval, SQL injection, hardcoded secrets…) |
| 3 | `QualityChecker` (AST) | Checks naming, type hints, anti-patterns, PEP 8 compliance |
| 4 | Ollama LLM | Deep-dive analysis with suggestions and refactored snippets |
| 5 | Report Aggregator | Scores code (0–100), assigns A–F grade, persists to history |

---

## ✨ Features

- 🔴 **Security scanning** — CWE-tagged vulnerabilities with fix suggestions
- ⚙️ **Structural analysis** — Cyclomatic complexity, function length, mutable defaults
- ✨ **Quality grading** — A–F letter grade with score breakdown
- 🧠 **LLM deep-dive** — Streaming analysis from a local Ollama model
- 📜 **Session memory** — Review history persisted to JSON, stats tracked
- 📁 **File upload** — Paste code or upload a `.py` file
- 🎨 **Premium dark UI** — Glassmorphism, animated step tracker, metric cards

---

## 🛠️ Tech Stack

- **Python 3.11+**
- **Streamlit** — UI framework
- **Ollama** — Local LLM inference (`qwen2.5-coder:1.5b` recommended)
- **AST** — Python's built-in Abstract Syntax Tree module
- **Requests** — Ollama HTTP API client

---

## ⚡ Quick Start

### 1. Clone the repo
```bash
git clone https://github.com/SaiVarshithh/AI-Agents.git
cd AI-Agents/05_Code_Review_Agent
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Start Ollama and pull a model
```bash
ollama serve
ollama pull qwen2.5-coder:1.5b
```

### 4. Run the app
```bash
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

---

## 🗂️ Project Structure

```
05_Code_Review_Agent/
├── app.py                    # Streamlit UI
├── code_review_agent.py      # Main agent orchestrator
├── tools/
│   ├── syntax_analyzer.py    # AST-based syntax & structure analysis
│   ├── security_checker.py   # Pattern + AST security scanning
│   └── quality_checker.py    # Quality scoring & best-practice checks
├── utils/
│   ├── ollama_client.py      # Ollama API wrapper (streaming + blocking)
│   └── memory.py             # File-based review history (JSON)
├── data/
│   └── review_history.json   # Auto-created on first run
├── requirements.txt
└── README.md
```

---

## 🎮 Example Usage

1. Click **"Load Sample (Buggy Code)"** to load a pre-built example with security issues
2. Click **🚀 Run Code Review**
3. Watch the 5-step agent pipeline execute in real time
4. Explore the **Security**, **Syntax**, **Quality** and **LLM Analysis** tabs

---

## 📸 Screenshots

> *(Add screenshots here after running the app)*

---

## 🔮 Roadmap

- [ ] JavaScript / TypeScript support
- [ ] Diff viewer (before/after refactoring)
- [ ] GitHub PR integration
- [ ] Export report as PDF

---

## 📄 License

MIT — free to use and modify.
