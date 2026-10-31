from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

import httpx

DEFAULT_MODEL = "qwen2.5-coder:7b"
DEFAULT_URL = "http://localhost:11434"


class LLMError(RuntimeError):
    """Raised for any problem talking to the local model."""


@dataclass
class LLMConfig:
    model: str = DEFAULT_MODEL
    base_url: str = DEFAULT_URL
    temperature: float = 0.2
    num_ctx: int = 4096 #prompt size
    timeout: float = 900.0  # seconds to wait for the model; CPU-only runs are slow


def _timeout(cfg: LLMConfig) -> httpx.Timeout:
    return httpx.Timeout(connect=5.0, read=cfg.timeout, write=30.0, pool=5.0)


def _unreachable(cfg: LLMConfig) -> LLMError:
    return LLMError(
        f"Cannot reach Ollama at {cfg.base_url}. "
        "Is it running? Open the Ollama app or run: ollama serve"
    )


def _raise_for_status(response: httpx.Response, cfg: LLMConfig) -> None:
    if response.status_code < 400:
        return
    response.read()
    try:
        detail = str(response.json().get("error", ""))
    except (ValueError, AttributeError):
        detail = response.text[:200]
    if response.status_code == 404 or "not found" in detail.lower():
        raise LLMError(f"Model '{cfg.model}' not found. Run: ollama pull {cfg.model}")
    raise LLMError(f"Ollama returned {response.status_code}: {detail or 'unknown error'}")


def _chat_stream(client, url, payload, cfg, on_token) -> str:
    parts: list[str] = []
    with client.stream("POST", url, json=payload) as response:
        _raise_for_status(response, cfg)
        for line in response.iter_lines():
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "error" in chunk:
                raise LLMError(str(chunk["error"]))
            token = chunk.get("message", {}).get("content", "")
            if token:
                parts.append(token)
                if on_token:
                    on_token(token)
            if chunk.get("done"):
                break
    return "".join(parts)


def chat(
    prompt: str,
    system: str | None = None,
    config: LLMConfig | None = None,
    stream: bool = False,
    on_token: Callable[[str], None] | None = None,
    client: httpx.Client | None = None,
) -> str:
    """Send one prompt to the local model and return its full reply."""
    cfg = config or LLMConfig()
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = {
        "model": cfg.model,
        "messages": messages,
        "stream": stream,
        "options": {"temperature": cfg.temperature, "num_ctx": cfg.num_ctx},
    }
    url = cfg.base_url.rstrip("/") + "/api/chat"

    owns_client = client is None
    client = client or httpx.Client(timeout=_timeout(cfg))
    try:
        if stream:
            return _chat_stream(client, url, payload, cfg, on_token)
        response = client.post(url, json=payload)
        _raise_for_status(response, cfg)
        return response.json().get("message", {}).get("content", "")
    except httpx.ConnectError as exc:
        raise _unreachable(cfg) from exc
    except httpx.TimeoutException as exc:
        raise LLMError(
            f"The model took longer than {cfg.timeout:.0f}s to respond. "
            "Try a smaller prompt or a smaller model."
        ) from exc
    finally:
        if owns_client:
            client.close()


def check_ollama(config: LLMConfig | None = None, client: httpx.Client | None = None) -> None:
    """Fail fast, with a helpful message, if Ollama or the model is unavailable."""
    cfg = config or LLMConfig()
    owns_client = client is None
    client = client or httpx.Client(timeout=_timeout(cfg))
    try:
        response = client.get(cfg.base_url.rstrip("/") + "/api/tags")
        _raise_for_status(response, cfg)
        names = {m.get("name", "") for m in response.json().get("models", [])}
    except httpx.ConnectError as exc:
        raise _unreachable(cfg) from exc
    finally:
        if owns_client:
            client.close()
    wanted = cfg.model if ":" in cfg.model else cfg.model + ":latest"
    if wanted not in names:
        raise LLMError(f"Model '{cfg.model}' is not installed. Run: ollama pull {cfg.model}")


if __name__ == "__main__":
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    question = " ".join(sys.argv[1:]) or "Say hello in five words."
    check_ollama()
    chat(question, stream=True, on_token=lambda t: print(t, end="", flush=True))
    print()