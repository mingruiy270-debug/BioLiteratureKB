"""OpenAI-compatible LLM 客户端（带重试）。密钥只允许在状态检查时显示 SET/MISSING。"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .config import Config

_RETRYABLE = (requests.exceptions.RequestException, json.JSONDecodeError, KeyError, ValueError)


class LLMNotConfigured(Exception):
    pass


class LLMClient:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.api_key = os.environ.get(cfg.llm_api_key_env, "")
        self.base_url = os.environ.get(cfg.llm_base_url_env, "")
        self.model = os.environ.get(cfg.llm_model_env, "")

    def configured(self) -> bool:
        return bool(self.api_key and self.base_url and self.model)

    def _chat_once(self, messages: List[Dict[str, str]], max_tokens: Optional[int]) -> str:
        url = self.base_url.rstrip("/") + "/chat/completions"
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.cfg.llm_temperature,
        }
        if max_tokens and max_tokens > 0:
            payload["max_tokens"] = max_tokens
        # deepseek-v4 系 thinking 模式（OpenAI SDK 对应 extra_body；直接放进请求体）
        if self.cfg.llm_thinking in ("enabled", "disabled"):
            payload["thinking"] = {"type": self.cfg.llm_thinking}
        if self.cfg.llm_reasoning_effort in ("low", "high", "max"):
            payload["reasoning_effort"] = self.cfg.llm_reasoning_effort
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=self.cfg.llm_timeout_seconds,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()

    @retry(
        retry=retry_if_exception_type(_RETRYABLE),
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        reraise=True,
    )
    def chat(self, messages: List[Dict[str, str]], max_tokens: Optional[int] = None) -> str:
        """max_tokens 缺省时使用 config 的 llm.max_tokens（默认 384000，thinking 模式下的模型上限）。"""
        if not self.configured():
            raise LLMNotConfigured("BIOKB_LLM_API_KEY / BASE_URL / MODEL 未配置")
        return self._chat_once(messages, max_tokens if max_tokens is not None else self.cfg.llm_max_tokens)

    def chat_json(self, messages: List[Dict[str, str]], max_tokens: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """要求模型只输出 JSON 对象，容错提取。"""
        text = self.chat(messages, max_tokens)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start, end = text.find("{"), text.rfind("}")
            if start != -1 and end > start:
                try:
                    return json.loads(text[start:end + 1])
                except json.JSONDecodeError:
                    pass
        return None
