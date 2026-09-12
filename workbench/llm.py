"""Thin wrapper around the local LiteLLM proxy (OpenAI-compatible, offline)."""
import subprocess
from typing import Optional

from openai import OpenAI

from . import config

client = OpenAI(api_key=config.LITELLM_API_KEY,
                base_url=config.LITELLM_BASE_URL,
                timeout=300)


def chat(model: str, messages: list, temperature: float = 0.2,
         max_tokens: int = 2048, timeout: Optional[float] = None) -> str:
    resp = client.chat.completions.create(
        model=model, messages=messages,
        temperature=temperature, max_tokens=max_tokens,
        timeout=timeout if timeout is not None else 300,
    )
    return resp.choices[0].message.content


def unload(logical_name: str) -> None:
    """Force Ollama to release a model's VRAM (mid-range GPU friendly)."""
    name = config.OLLAMA_NAMES.get(logical_name)
    if name:
        subprocess.run(["ollama", "stop", name], capture_output=True)
