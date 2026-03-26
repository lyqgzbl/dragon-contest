from collections.abc import Mapping, Sequence
from typing import Any, cast
from azure.ai.inference.aio import ChatCompletionsClient
from azure.ai.inference.models import ChatRequestMessage
from azure.core.credentials import AzureKeyCredential


class OpenAIHandler:
    def __init__(
        self,
        api_key: str,
        endpoint: str,
        model_name: str,
        temperature: float,
        top_p: float,
    ):
        self.client = ChatCompletionsClient(
            endpoint=endpoint, credential=AzureKeyCredential(api_key)
        )
        self.api_key = api_key
        self.endpoint = endpoint
        self.model_name = model_name
        self.temperature = temperature
        self.top_p = top_p

    async def get_response(
        self,
        messages: Sequence[ChatRequestMessage | Mapping[str, Any]],
    ) -> str:
        request_messages = cast(list[ChatRequestMessage], list(messages))
        response = await self.client.complete(
            messages=request_messages,
            model=self.model_name,
            temperature=self.temperature,
            top_p=self.top_p,
        )
        choices = response.choices
        if not choices:
            raise ValueError("GitHub Models returned no choices")
        content = choices[0].message.content
        if not content:
            raise ValueError("GitHub Models returned empty content")
        return content
