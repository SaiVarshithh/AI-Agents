"""
Ollama API client — streaming-first, with a hard timeout per token chunk.
"""
import json
import requests
from typing import Generator, Optional
from utils.logger import get_logger

log = get_logger("ollama")

OLLAMA_BASE_URL = "http://localhost:11434"
_CONNECT_TIMEOUT = 5      # seconds to establish connection
_READ_TIMEOUT    = 60     # seconds to wait for the next chunk


def is_ollama_running() -> bool:
    try:
        r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=_CONNECT_TIMEOUT)
        ok = r.status_code == 200
        log.debug("Ollama health check — online=%s", ok)
        return ok
    except Exception as e:
        log.debug("Ollama health check failed — %s", e)
        return False


def get_available_models() -> list[str]:
    try:
        r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=_CONNECT_TIMEOUT)
        if r.status_code == 200:
            names = [m["name"] for m in r.json().get("models", [])]
            log.info("Available models: %s", names)
            return names
    except Exception as e:
        log.warning("Could not fetch models: %s", e)
    return []


def chat(
    prompt: str,
    model: str = "qwen3:4b",
    system: Optional[str] = None,
    temperature: float = 0.2,
    stream: bool = True,
) -> str | Generator[str, None, None]:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": stream,
        "options": {"temperature": temperature, "num_predict": 2048},
    }
    if system:
        payload["system"] = system

    if stream:
        log.info("Sending STREAM request — model=%s  prompt_chars=%d", model, len(prompt))
        return _stream(payload)
    else:
        log.info("Sending BLOCKING request — model=%s  prompt_chars=%d", model, len(prompt))
        return _blocking(payload)


def _stream(payload: dict) -> Generator[str, None, None]:
    """Yield tokens as they arrive. Uses per-chunk read timeout so UI never freezes."""
    try:
        with requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json=payload,
            stream=True,
            timeout=(_CONNECT_TIMEOUT, _READ_TIMEOUT),
        ) as resp:
            resp.raise_for_status()
            log.debug("Stream connection established")
            for line in resp.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line)
                        token = chunk.get("response", "")
                        if token:
                            yield token
                        if chunk.get("done"):
                            log.debug("Stream finished (done=true received)")
                            break
                    except json.JSONDecodeError:
                        continue
    except requests.exceptions.ConnectionError as e:
        log.error("Ollama connection error: %s", e)
        yield "\n\n⚠️ Could not connect to Ollama. Is it running?"
    except requests.exceptions.Timeout:
        log.error("Ollama stream timed out after %ds waiting for next token", _READ_TIMEOUT)
        yield "\n\n⚠️ Ollama timed out waiting for the next token. Try a smaller model."
    except Exception as e:
        log.error("Unexpected stream error: %s", e)
        yield f"\n\n⚠️ Stream error: {e}"


def _blocking(payload: dict) -> str:
    """Non-streaming fallback. Use only for internal calls, not the UI."""
    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json=payload,
            timeout=(_CONNECT_TIMEOUT, 90),
        )
        resp.raise_for_status()
        full = ""
        for line in resp.text.strip().splitlines():
            try:
                chunk = json.loads(line)
                full += chunk.get("response", "")
                if chunk.get("done"):
                    break
            except json.JSONDecodeError:
                continue
        return full.strip()
    except requests.exceptions.Timeout:
        return "⚠️ Ollama request timed out."
    except Exception as e:
        return f"⚠️ Ollama error: {e}"