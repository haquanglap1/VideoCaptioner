"""A job owns its HTTP task/socket, credentials and finite request deadline."""

import asyncio
from dataclasses import dataclass, field
from typing import Callable

import openai

from .client import LLMCredentials
from .rate_limit import RateLimitGate, rate_limit_error, request_gate
from .request_logger import OwnedRequestLog
from .request_policy import validate_request_timeout


@dataclass(frozen=True)
class OwnedLLMRequest:
    credentials: LLMCredentials
    timeout: int = 120
    cancelled: Callable[[], bool] = lambda: False
    log_content: bool = True
    _gate: RateLimitGate = field(default_factory=request_gate, init=False, repr=False, compare=False)

    def __post_init__(self):
        validate_request_timeout(self.timeout)

    def __call__(self, messages, model, **kwargs):
        def check(deadline: float | None):
            if self.cancelled():
                raise RuntimeError("Translation cancelled.")
            if deadline is not None and asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError

        if self.cancelled():
            raise RuntimeError("Translation cancelled.")
        if not self.credentials.is_complete:
            raise ValueError("LLM credentials are not configured.")

        async def attempt(deadline):
            async with openai.AsyncOpenAI(
                api_key=self.credentials.api_key, base_url=self.credentials.base_url,
                max_retries=0, timeout=self.timeout,
                http_client=openai.DefaultAsyncHttpxClient(follow_redirects=False, trust_env=False, timeout=self.timeout),
            ) as client:
                check(deadline)
                log = OwnedRequestLog(self.credentials.base_url, model, messages, kwargs,
                                      log_content=self.log_content, secret=self.credentials.api_key)
                task = asyncio.create_task(client.chat.completions.create(model=model, messages=messages, **kwargs))
                try:
                    while not task.done():
                        check(deadline)
                        await asyncio.wait({task}, timeout=0.1)
                    check(deadline)
                    response = await task
                    log.finish(response, status=200)
                    return response
                except BaseException as exc:
                    outcome = ("cancelled" if self.cancelled() or isinstance(exc, asyncio.CancelledError)
                               else "timeout" if isinstance(exc, (TimeoutError, openai.APITimeoutError))
                               else "http_error" if isinstance(exc, openai.APIStatusError) else "error")
                    log.finish(status=exc.status_code if isinstance(exc, openai.APIStatusError) else None,
                               outcome=outcome, error_type=type(exc).__name__,
                               rejection_kind=rate_limit_error(exc).kind if isinstance(exc, openai.RateLimitError) else "")
                    raise
                finally:
                    if not task.done():
                        task.cancel()
                    await asyncio.gather(task, return_exceptions=True)

        async def request():
            deadline = None
            while True:
                check(deadline)
                while not self._gate.enter():
                    check(deadline)
                    await asyncio.sleep(.1)
                # Admission is an executor queue, not a sent provider request.
                # Recovery waits after the first POST still share its deadline.
                if deadline is None:
                    deadline = asyncio.get_running_loop().time() + self.timeout
                try:
                    return await attempt(deadline)
                except openai.RateLimitError as exc:
                    self._gate.reject(rate_limit_error(exc), deadline - asyncio.get_running_loop().time())
                finally:
                    self._gate.leave()
        try:
            return asyncio.run(request())
        except openai.APIStatusError as exc:
            raise RuntimeError(f"Translation HTTP {exc.status_code}; review or retry explicitly.") from None
        except (openai.APIConnectionError, TimeoutError):
            raise RuntimeError("Translation timed out or lost connection; retry explicitly. Provider processing/charges may continue.") from None
