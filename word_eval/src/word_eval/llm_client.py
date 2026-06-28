"""LLM API 客户端，基于 OpenAI SDK。"""

import asyncio
import logging
from typing import Any

from openai import AsyncOpenAI, APIError, APITimeoutError, APIConnectionError

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_TIMEOUT = 120
DEFAULT_MAX_RETRIES = 3
RETRY_DELAY = 2


class LLMClient:
    """异步 LLM API 客户端，基于 OpenAI SDK，支持并发请求和自动重试。"""

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        max_concurrency: int = 3,
        timeout: int = DEFAULT_TIMEOUT,
        stream: bool = False,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        self.model = model
        self.stream = stream
        self._max_retries = max_retries
        self._semaphore = asyncio.Semaphore(max_concurrency)

        # 如果 base_url 以 /chat/completions 结尾，截断（SDK 会自动追加）
        base = base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            base = base[: -len("/chat/completions")]

        # CNB API 需要特殊 Accept header
        extra_headers = {}
        if "cnb.cool" in base:
            extra_headers["Accept"] = "application/vnd.cnb.api+json"

        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base,
            timeout=timeout,
            default_headers=extra_headers,
            max_retries=0,  # 手动控制重试
        )
        self._stats = {"total_calls": 0, "total_tokens": 0, "failed_calls": 0}

    def _build_messages(self, system_prompt: str, user_message: str) -> list[dict]:
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

    async def _call_stream(self, system_prompt: str, user_message: str) -> dict[str, Any]:
        """流式 API 调用，通过 SSE 读取并重组完整响应。"""
        messages = self._build_messages(system_prompt, user_message)

        full_content = ""
        usage_data = {}

        stream = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.1,
            stream=True,
            stream_options={"include_usage": True},
        )

        async for chunk in stream:
            if chunk.usage:
                usage_data = chunk.usage.model_dump()
            if chunk.choices and chunk.choices[0].delta.content:
                full_content += chunk.choices[0].delta.content

        self._stats["total_calls"] += 1
        tokens = usage_data.get("total_tokens", 0)
        self._stats["total_tokens"] += tokens

        return {
            "choices": [{"message": {"content": full_content.strip()}}],
            "usage": usage_data,
        }

    async def _call_once(
        self, system_prompt: str, user_message: str
    ) -> dict[str, Any]:
        if self.stream:
            return await self._call_stream(system_prompt, user_message)

        messages = self._build_messages(system_prompt, user_message)

        completion = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.1,
            stream=False,
        )

        usage = completion.usage.model_dump() if completion.usage else {}
        content = completion.choices[0].message.content or ""

        self._stats["total_calls"] += 1
        self._stats["total_tokens"] += usage.get("total_tokens", 0)

        return {
            "choices": [{"message": {"content": content}}],
            "usage": usage,
        }

    async def call(
        self, system_prompt: str, user_message: str
    ) -> dict[str, Any]:
        """带重试和并发控制的 API 调用。"""
        async with self._semaphore:
            for attempt in range(self._max_retries):
                try:
                    return await self._call_once(system_prompt, user_message)
                except (APIError, APITimeoutError, APIConnectionError) as e:
                    self._stats["failed_calls"] += 1
                    logger.warning(
                        "API 调用失败 (尝试 %d/%d): %s",
                        attempt + 1,
                        self._max_retries,
                        e,
                    )
                    if attempt < self._max_retries - 1:
                        wait = RETRY_DELAY * (attempt + 1)
                        await asyncio.sleep(wait)
                    else:
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
        await self._client.close()
