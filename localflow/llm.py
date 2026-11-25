"""Tiny client for a local Ollama server."""
from __future__ import annotations

import requests

from .config import settings


class LLMError(RuntimeError):
    pass


def chat(system: str, user: str, model: str | None = None, temperature: float = 0.0,
         timeout: float = 60, max_tokens: int = 1024) -> str:
    url = settings["ollama_url"].rstrip("/") + "/api/chat"
    payload = {
        "model": model or settings["llm_model"],
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": False,
        "keep_alive": "30m",
        "options": {"temperature": temperature, "num_predict": max_tokens, "num_ctx": 8192},
    }
    try:
        r = requests.post(url, json=payload, timeout=timeout)
        r.raise_for_status()
        return (r.json().get("message", {}).get("content") or "").strip()
    except Exception as exc:
        raise LLMError(str(exc)) from exc


def embed(text: str, model: str = "nomic-embed-text") -> list[float]:
    url = settings["ollama_url"].rstrip("/") + "/api/embed"
    try:
        r = requests.post(url, json={"model": model, "input": text[:8000]}, timeout=60)
        r.raise_for_status()
        return r.json()["embeddings"][0]
    except Exception as exc:
        raise LLMError(str(exc)) from exc


def available_models() -> list[str]:
    try:
        r = requests.get(settings["ollama_url"].rstrip("/") + "/api/tags", timeout=3)
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []


def warm_up() -> None:
    try:
        chat("Reply with OK.", "OK", max_tokens=2, timeout=120)
    except LLMError:
        pass
