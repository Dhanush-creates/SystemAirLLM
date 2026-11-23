"""Model providers. Any OpenAI-compatible server (Ollama, vLLM, llama.cpp) plus a mock."""
from __future__ import annotations

import importlib.util
import json
import os
import urllib.error
import urllib.request
import time
from pathlib import Path
from typing import Callable

from .netguard import check_local
from .registry import Registry

MAX_REPLY_TOKENS = 3000

# No proxies: a system proxy would route local calls off the machine.
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class OpenAIProvider:
    def __init__(self, base_url: str, allow_private: bool = False, timeout: int = 300, no_think=()):
        check_local(base_url, allow_private)
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.no_think = set(no_think)  # models run with hidden reasoning switched off (registry: think: false)
        self._models_cache: set[str] | None = None
        self._models_cache_at = 0.0

    def _request(self, path: str, payload: dict | None = None, timeout: int | None = None) -> dict:
        req = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={"Content-Type": "application/json", "Authorization": "Bearer local"},
        )
        try:
            with _opener.open(req, timeout=timeout or self.timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:  # keep the server's explanation
            raise OSError(f"HTTP {e.code}: {e.read().decode(errors='replace')[:300]}") from e

    def _once(self, model: str, messages: list[dict], json_mode: bool, think: bool) -> str:
        # max_tokens bounds every reply: in JSON mode a model can otherwise emit whitespace without end.
        body = {"model": model, "messages": messages, "temperature": 0.2, "stream": False,
                "max_tokens": MAX_REPLY_TOKENS}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if not think:
            body["reasoning_effort"] = "none"
        return self._request("/chat/completions", body)["choices"][0]["message"]["content"] or ""

    def chat(self, model: str, messages: list[dict], json_mode: bool = False, think: bool | None = None) -> str:
        """One reply. A reasoning model can spend its whole budget on hidden reasoning and return
        nothing (seen on qwen3:4b), so an empty reply is retried with reasoning switched off, and
        once more without JSON mode, which avoids a repeated-token abort on small models."""
        if think is None:  # the caller may override the registry setting for one call
            think = model not in self.no_think
        attempts = [(json_mode, think), (json_mode, False), (False, False)]
        error: Exception | None = None
        for as_json, thinking in dict.fromkeys(attempts):  # de-duplicated, order kept
            try:
                reply = self._once(model, messages, as_json, thinking)
            except OSError as e:
                if error is None and thinking:  # the server itself failed on the first, normal call
                    raise
                error = e
                continue
            if reply.strip():
                return reply
            error = error or OSError("the model returned an empty reply")
        raise error or OSError("the model returned an empty reply")

    def available(self, model: str) -> bool:
        now = time.monotonic()
        if self._models_cache is not None and now - self._models_cache_at < 5:
            return model in self._models_cache
        try:
            data = self._request("/models", timeout=2).get("data")
            if not isinstance(data, list):
                raise ValueError("model server returned an invalid model list")
            self._models_cache = {m["id"] for m in data if isinstance(m, dict) and isinstance(m.get("id"), str)}
            self._models_cache_at = now
            return model in self._models_cache
        except (OSError, KeyError, ValueError):
            self._models_cache = set()
            self._models_cache_at = now
            return False


class MockProvider:
    """Scripted replies for tests: a list consumed in order, or fn(model, messages) -> str."""

    def __init__(self, script: list[str] | Callable[[str, list[dict]], str] | None = None):
        self.script = script

    def chat(self, model: str, messages: list[dict], json_mode: bool = False, think: bool | None = None) -> str:
        if callable(self.script):
            return self.script(model, messages)
        if self.script:
            return self.script.pop(0)
        return json.dumps({"final": f"[mock:{model}] {messages[-1]['content'][:80]}"})

    def available(self, model: str) -> bool:
        return True


class AirLLMProvider:
    """Optional: runs a model far larger than the GPU by loading one layer at a time.

    Very slow, so its models are marked escalation_only and used when smaller models
    fail. Off unless `enabled: true` in the config or WORKBENCH_AIRLLM=1. Weights are
    read from a local folder only; the Hugging Face hub is forced offline.
    """

    def __init__(self, cfg: dict):
        self.enabled = bool(cfg.get("enabled")) or os.environ.get("WORKBENCH_AIRLLM") == "1"
        self.paths = cfg.get("paths") or {}
        self.compression = cfg.get("compression", "4bit")
        self.max_new_tokens = cfg.get("max_new_tokens", 512)
        self._loaded: dict = {}

    def available(self, model: str) -> bool:
        path = self.paths.get(model)
        return bool(self.enabled and path and Path(path).is_dir()
                    and importlib.util.find_spec("airllm") is not None)

    def _load(self, model: str):
        if model not in self._loaded:
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ["TRANSFORMERS_OFFLINE"] = "1"
            from airllm import AutoModel
            self._loaded = {model: AutoModel.from_pretrained(self.paths[model], compression=self.compression)}
        return self._loaded[model]

    def chat(self, model: str, messages: list[dict], json_mode: bool = False, think: bool | None = None) -> str:
        m = self._load(model)
        prompt = m.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        ids = m.tokenizer(prompt, return_tensors="pt", return_attention_mask=False)["input_ids"].cuda()
        out = m.generate(ids, max_new_tokens=self.max_new_tokens, use_cache=True, return_dict_in_generate=True)
        return m.tokenizer.decode(out.sequences[0][ids.shape[1]:], skip_special_tokens=True)


def build_providers(registry: Registry) -> dict:
    out = {}
    for name, cfg in registry.providers.items():
        if cfg["type"] == "mock":
            out[name] = MockProvider()
        elif cfg["type"] == "airllm":
            out[name] = AirLLMProvider(cfg)
        else:
            out[name] = OpenAIProvider(cfg["base_url"], registry.allow_private_network,
                                       no_think=[m.id for m in registry.models if not m.think])
    return out
