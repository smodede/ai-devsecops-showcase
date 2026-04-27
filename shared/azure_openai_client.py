"""
Azure OpenAI client wrapper.

Provides a thin, reusable layer over the openai SDK configured for Azure,
with retry logic and structured logging.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from openai import AzureOpenAI

logger = logging.getLogger(__name__)


def _get_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise EnvironmentError(
            f"Required environment variable '{name}' is not set. "
            "Check your .env file or pipeline variable group."
        )
    return value


class AzureOpenAIClient:
    """Thin wrapper around the Azure OpenAI SDK for chat and embeddings."""

    def __init__(
        self,
        endpoint: str | None = None,
        api_key: str | None = None,
        api_version: str | None = None,
        deployment: str | None = None,
        embedding_deployment: str | None = None,
    ) -> None:
        self.endpoint = endpoint or _get_env("AZURE_OPENAI_ENDPOINT")
        self.api_key = api_key or _get_env("AZURE_OPENAI_API_KEY")
        self.api_version = api_version or os.environ.get(
            "AZURE_OPENAI_API_VERSION", "2024-02-01"
        )
        self.deployment = deployment or _get_env("AZURE_OPENAI_DEPLOYMENT")
        self.embedding_deployment = embedding_deployment or os.environ.get(
            "AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-ada-002"
        )

        self._client = AzureOpenAI(
            azure_endpoint=self.endpoint,
            api_key=self.api_key,
            api_version=self.api_version,
        )
        logger.info(
            "AzureOpenAIClient initialised (deployment=%s, api_version=%s)",
            self.deployment,
            self.api_version,
        )

    # ------------------------------------------------------------------
    # Chat completion
    # ------------------------------------------------------------------

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> str:
        """
        Send a chat completion request and return the assistant message content.

        Args:
            messages: List of role/content dicts (system, user, assistant).
            temperature: Sampling temperature (defaults to GPT_TEMPERATURE env var).
            max_tokens: Maximum tokens in response (defaults to GPT_MAX_TOKENS env var).
            **kwargs: Additional parameters forwarded to the API.

        Returns:
            Assistant message content as a string.
        """
        temperature = temperature if temperature is not None else float(
            os.environ.get("GPT_TEMPERATURE", "0.2")
        )
        max_tokens = max_tokens or int(os.environ.get("GPT_MAX_TOKENS", "2000"))

        logger.debug(
            "Chat request: deployment=%s, messages=%d, temperature=%s",
            self.deployment,
            len(messages),
            temperature,
        )

        response = self._client.chat.completions.create(
            model=self.deployment,
            messages=messages,  # type: ignore[arg-type]
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

        content: str = response.choices[0].message.content or ""
        logger.debug("Chat response: %d chars", len(content))
        return content

    # ------------------------------------------------------------------
    # Embeddings
    # ------------------------------------------------------------------

    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for a list of text strings.

        Args:
            texts: List of strings to embed.

        Returns:
            List of embedding vectors (one per input text).
        """
        logger.debug(
            "Embedding request: deployment=%s, count=%d",
            self.embedding_deployment,
            len(texts),
        )

        response = self._client.embeddings.create(
            model=self.embedding_deployment,
            input=texts,
        )

        vectors = [item.embedding for item in response.data]
        logger.debug("Embeddings received: count=%d, dims=%d", len(vectors), len(vectors[0]) if vectors else 0)
        return vectors
