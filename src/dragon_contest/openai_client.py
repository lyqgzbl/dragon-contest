from collections.abc import Iterable
from typing import Any
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam


class OpenAIHandler:
    def __init__(
        self,
        api_key: str,
        base_url: str | None,
        model_name: str,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ):
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=30.0,
            max_retries=2,
        )
        self.api_key = api_key
        self.base_url = base_url
        self.model_name = model_name
        self.temperature = temperature
        self.top_p = top_p

    async def get_response(
        self,
        messages: Iterable[ChatCompletionMessageParam] | Iterable[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
        max_tokens: int | None = 1000,
    ) -> str:
        kwargs: dict[str, Any] = {
            "messages": messages,
            "model": self.model_name,
            "temperature": self.temperature,
            "top_p": self.top_p,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        response = await self.client.chat.completions.create(**kwargs)
        choices = response.choices
        if not choices:
            raise ValueError("OpenAI API returned no choices")
        content = choices[0].message.content
        if not content:
            raise ValueError("OpenAI API returned empty content")
        return content

    async def close(self) -> None:
        await self.client.close()
