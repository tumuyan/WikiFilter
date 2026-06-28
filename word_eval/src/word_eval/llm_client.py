"""LLM API 客户端，支持 OpenAI 兼容接口（流式和非流式）。"""

import asyncio
import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_TIMEOUT = 120
MAX_RETRIES = 3
RETRY_DELAY = 2


class LLMClient:
    """异步 LLM API 客户端，支持并发请求和自动重试。"""

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        max_concurrency: int = 3,
        timeout: int = DEFAULT_TIMEOUT,
        stream: bool = False,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.stream = stream
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._client = httpx.AsyncClient(timeout=timeout)
        base = base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            self._chat_url = base
        else:
            self._chat_url = f"{base}/v1/chat/completions"
        self._stats = {"total_calls": 0, "total_tokens": 0, "failed_calls": 0}

    def _build_payload(self, system_prompt: str, user_message: str) -> dict:
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.1,
            "max_tokens": 4096,
            "stream": self.stream,
        }

    def _build_headers(self) -> dict:
        accept = "application/vnd.cnb.api+json" if "cnb.cool" in self._chat_url else "application/json"
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": accept,
        }

    async def _call_stream(self, system_prompt: str, user_message: str) -> dict[str, Any]:
        """流式 API 调用，通过 SSE 读取并重组完整响应。"""
        headers = self._build_headers()
        payload = self._build_payload(system_prompt, user_message)

        async with self._client.stream("POST", self._chat_url, headers=headers, json=payload) as resp:
            resp.raise_for_status()
            full_content = ""
            usage_data = {}
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                choices = chunk.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        full_content += content
                # 部分实现在最后一个 chunk 中返回 usage
                usage = chunk.get("usage", {})
                if usage:
                    usage_data = usage

            self._stats["total_calls"] += 1
            tokens = usage_data.get("total_tokens", 0)
            self._stats["total_tokens"] += tokens

            # 构造标准 OpenAI 响应格式
            return {
                "choices": [{"message": {"content": full_content.strip()}}],
                "usage": usage_data,
            }

    async def _call_once(
        self, system_prompt: str, user_message: str
    ) -> dict[str, Any]:
        if self.stream:
            return await self._call_stream(system_prompt, user_message)

        headers = self._build_headers()
        payload = self._build_payload(system_prompt, user_message)

        resp = await self._client.post(
            self._chat_url,
            headers=headers,
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

        usage = data.get("usage", {})
        self._stats["total_calls"] += 1
        self._stats["total_tokens"] += usage.get("total_tokens", 0)

        return data

    async def call(
        self, system_prompt: str, user_message: str
    ) -> dict[str, Any]:
        """带重试和并发控制的 API 调用。"""
        async with self._semaphore:
            for attempt in range(MAX_RETRIES):
                try:
                    return await self._call_once(system_prompt, user_message)
                except (httpx.HTTPStatusError, httpx.TimeoutException) as e:
                    self._stats["failed_calls"] += 1
                    logger.warning(
                        "API 调用失败 (尝试 %d/%d): %s",
                        attempt + 1,
                        MAX_RETRIES,
                        e,
                    )
                    if attempt < MAX_RETRIES - 1:
                        wait = RETRY_DELAY * (attempt + 1)
                        await asyncio.sleep(wait)
                    else:
                        raise
                except Exception:
                    raise

    def extract_content(self, response: dict[str, Any]) -> str:
        """从 API 响应中提取文本内容。"""
        choices = response.get("choices", [])
        if not choices:
            raise ValueError("API 响应中没有 choices")
        message = choices[0].get("message", {})
        content = message.get("content", "")
        return content.strip()

    @property
    def stats(self) -> dict[str, int]:
        return dict(self._stats)

    async def close(self) -> None:
        await self._client.aclose()
