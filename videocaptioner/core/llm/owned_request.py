"""A job owns its HTTP task/socket, credentials and finite request deadline."""

import asyncio
from dataclasses import dataclass
from typing import Callable

import openai

from .client import LLMCredentials
from .request_policy import validate_request_timeout


@dataclass(frozen=True)
class OwnedLLMRequest:
    credentials: LLMCredentials
    timeout: int = 120
    cancelled: Callable[[], bool] = lambda: False

    def __post_init__(self):
        validate_request_timeout(self.timeout)

    def __call__(self, messages, model, **kwargs):
        def check(deadline: float):
            if self.cancelled():
                raise RuntimeError("Translation cancelled.")
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError

        if self.cancelled():
            raise RuntimeError("Translation cancelled.")
        if not self.credentials.is_complete:
            raise ValueError("LLM credentials are not configured.")

        async def request():
            deadline = asyncio.get_running_loop().time() + self.timeout
            async with openai.AsyncOpenAI(
                api_key=self.credentials.api_key, base_url=self.credentials.base_url,
                max_retries=0, timeout=self.timeout,
                http_client=openai.DefaultAsyncHttpxClient(follow_redirects=False, trust_env=False, timeout=self.timeout),
            ) as client:
                check(deadline)
                task = asyncio.create_task(client.chat.completions.create(model=model, messages=messages, **kwargs))
                try:
                    while not task.done():
                        check(deadline)
                        await asyncio.wait({task}, timeout=0.1)
                    check(deadline)
                    return await task
                finally:
                    if not task.done():
                        task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
        try:
            return asyncio.run(request())
        except openai.APIStatusError as exc:
            raise RuntimeError(f"Translation HTTP {exc.status_code}; review or retry explicitly.") from None
        except (openai.APIConnectionError, TimeoutError):
            raise RuntimeError("Translation timed out or lost connection; retry explicitly. Provider processing/charges may continue.") from None
