import asyncio
import logging
import random
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from functools import lru_cache

from app.core.config import settings
from app.llm.base import ChatMessage, LLMProvider, ProviderError, StreamPart, Usage
from app.llm.router import ModelRouter, RouterRules

logger = logging.getLogger(__name__)

AUTO_MODEL = "auto"


class RequestTimeout(ProviderError):
    """The whole request ran past its deadline, so no retry or fallback is attempted."""

    def __init__(self, seconds: float) -> None:
        super().__init__(f"request timed out after {seconds:g}s", retryable=False)


@dataclass(frozen=True)
class ModelInfo:
    id: str
    provider: str


@dataclass(frozen=True)
class Chunk:
    model: str  # the model that actually produced this text (may be a fallback)
    text: str
    usage: Usage | None = None  # set on the chunk that carries token counts (text is "")


class CircuitBreaker:
    """Stops calling a provider for a while after too many failures in a row."""

    def __init__(
        self, threshold: int, cooldown: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.threshold = threshold
        self.cooldown = cooldown
        self.clock = clock
        self.failures = 0
        self.opened_at: float | None = None

    def allow(self) -> bool:
        if self.opened_at is None:
            return True
        # after the cooldown we let one request through to test the provider again
        if self.clock() - self.opened_at >= self.cooldown:
            self.opened_at = None
            self.failures = self.threshold - 1
            return True
        return False

    def record_success(self) -> None:
        self.failures = 0
        self.opened_at = None

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold:
            self.opened_at = self.clock()


class Gateway:
    def __init__(
        self,
        models: dict[str, LLMProvider],
        *,
        default_model: str | None = None,
        fallback_models: list[str] | None = None,
        max_retries: int = 2,
        retry_base_delay: float = 0.5,
        retry_max_delay: float = 8.0,
        breaker_threshold: int = 5,
        breaker_cooldown: float = 30.0,
        idle_timeout: float | None = None,
        total_timeout: float | None = None,
        router: ModelRouter | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.models = models
        self.idle_timeout = idle_timeout
        self.total_timeout = total_timeout
        self.router = router
        self.fallback_models = [m for m in (fallback_models or []) if m in models]
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        self.retry_max_delay = retry_max_delay
        self.sleep = sleep
        self.breakers = {
            p.name: CircuitBreaker(breaker_threshold, breaker_cooldown) for p in models.values()
        }
        if default_model and (self.has_model(default_model) or self.can_route(default_model)):
            self.default_model: str | None = default_model
        else:
            self.default_model = next(iter(models), None)

    def list_models(self) -> list[ModelInfo]:
        infos = [ModelInfo(id=name, provider=p.name) for name, p in self.models.items()]
        if self.router is not None:
            infos.insert(0, ModelInfo(id=AUTO_MODEL, provider="router"))
        return infos

    def can_route(self, model: str) -> bool:
        return model == AUTO_MODEL and self.router is not None

    def has_model(self, model: str) -> bool:
        return model in self.models

    def backoff(self, attempt: int) -> float:
        # exponential backoff with full jitter so clients don't retry in lockstep
        cap = min(self.retry_max_delay, self.retry_base_delay * 2**attempt)
        return random.uniform(0, cap)

    async def _next_part(
        self, parts: AsyncIterator[StreamPart], name: str, deadline: float | None
    ) -> StreamPart:
        loop = asyncio.get_running_loop()
        wait = self.idle_timeout
        if deadline is not None:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise RequestTimeout(self.total_timeout or 0)
            wait = remaining if wait is None else min(wait, remaining)
        try:
            return await asyncio.wait_for(anext(parts), wait)
        except TimeoutError:
            if deadline is not None and loop.time() >= deadline:
                raise RequestTimeout(self.total_timeout or 0) from None
            # a stalled stream is often a stuck connection, worth one more try
            raise ProviderError(
                f"{name} sent nothing for {self.idle_timeout:g}s", retryable=True
            ) from None

    async def stream(self, model: str, messages: list[ChatMessage]) -> AsyncIterator[Chunk]:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.total_timeout if self.total_timeout else None
        candidates = [model] + [m for m in self.fallback_models if m != model]
        last_error: ProviderError | None = None

        for name in candidates:
            provider = self.models[name]
            breaker = self.breakers[provider.name]
            if not breaker.allow():
                logger.warning("skipping %s, %s circuit is open", name, provider.name)
                last_error = ProviderError(f"{provider.name} is temporarily unavailable")
                continue

            for attempt in range(self.max_retries + 1):
                started = False
                parts = aiter(provider.stream(name, messages))
                try:
                    while True:
                        try:
                            part = await self._next_part(parts, name, deadline)
                        except StopAsyncIteration:
                            break
                        if isinstance(part, Usage):
                            yield Chunk(model=name, text="", usage=part)
                            continue
                        started = True
                        yield Chunk(model=name, text=part)
                    breaker.record_success()
                    return
                except RequestTimeout:
                    breaker.record_failure()
                    raise
                except ProviderError as err:
                    last_error = err
                    logger.warning("%s attempt %d failed: %s", name, attempt + 1, err)
                    # once text has reached the user we can't restart without duplicating it
                    if started:
                        breaker.record_failure()
                        raise
                    if not err.retryable or attempt == self.max_retries:
                        breaker.record_failure()
                        break
                    delay = self.backoff(attempt)
                    if deadline is not None:
                        delay = min(delay, max(0.0, deadline - loop.time()))
                    await self.sleep(delay)
                finally:
                    # close the provider stream so its http connection is released
                    aclose = getattr(parts, "aclose", None)
                    if aclose is not None:
                        await aclose()

        raise last_error or ProviderError("no model available")


def build_gateway() -> Gateway:
    # imported here so the sdks only load when the gateway is actually built
    from app.llm.echo_provider import EchoProvider
    from app.llm.gemini_provider import GeminiProvider
    from app.llm.openai_provider import OpenAIProvider

    models: dict[str, LLMProvider] = {}
    if settings.openai_api_key:
        openai_provider = OpenAIProvider(
            settings.openai_api_key,
            settings.llm_timeout_seconds,
            settings.openai_base_url,
            name=settings.openai_provider_name,
        )
        for m in settings.openai_models:
            models[m] = openai_provider
    if settings.gemini_api_key:
        gemini_provider = GeminiProvider(settings.gemini_api_key, settings.llm_timeout_seconds)
        for m in settings.gemini_models:
            models[m] = gemini_provider
    if settings.enable_echo_model:
        models["sage-echo"] = EchoProvider()

    if not models:
        logger.warning("no llm providers configured, chat will be unavailable")
    else:
        logger.info("llm models available: %s", ", ".join(models))

    router = None
    simple = settings.router_simple_model or settings.default_model or next(iter(models), None)
    complex_ = settings.router_complex_model or simple
    if simple in models and complex_ in models:
        router = ModelRouter(
            RouterRules(
                simple_model=simple,
                complex_model=complex_,
                threshold=settings.router_threshold,
                long_prompt_chars=settings.router_long_prompt_chars,
                very_long_prompt_chars=settings.router_very_long_prompt_chars,
                long_history_messages=settings.router_long_history_messages,
                keywords=tuple(k.lower() for k in settings.router_keywords),
            )
        )
        logger.info("auto routing: simple=%s complex=%s", simple, complex_)

    return Gateway(
        models,
        default_model=settings.default_model,
        fallback_models=settings.fallback_models,
        max_retries=settings.llm_max_retries,
        retry_base_delay=settings.llm_retry_base_delay,
        retry_max_delay=settings.llm_retry_max_delay,
        breaker_threshold=settings.circuit_breaker_threshold,
        breaker_cooldown=settings.circuit_breaker_cooldown_seconds,
        idle_timeout=settings.llm_idle_timeout_seconds or None,
        total_timeout=settings.llm_total_timeout_seconds or None,
        router=router,
    )


@lru_cache
def get_gateway() -> Gateway:
    return build_gateway()
