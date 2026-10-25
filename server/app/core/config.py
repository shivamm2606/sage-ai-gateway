from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "sage"
    environment: Literal["development", "production", "test"] = "development"
    debug: bool = False
    log_level: str = "INFO"
    cors_origins: list[str] = ["http://localhost:5173"]
    database_url: str  # no default — must be set in .env
    jwt_secret: str  # secret key used to sign access tokens
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # llm providers, a provider is only enabled when its key is set
    openai_api_key: str | None = None
    openai_base_url: str | None = None  # point at any openai-compatible api (groq, openrouter)
    openai_provider_name: str = "openai"  # label shown in the ui, e.g. "groq"
    openai_models: list[str] = ["gpt-4o-mini", "gpt-4o"]
    gemini_api_key: str | None = None
    gemini_models: list[str] = ["gemini-3.5-flash", "gemini-flash-lite-latest"]
    enable_echo_model: bool = True  # offline model for local dev, turn off in production

    # gateway behaviour
    default_model: str | None = None  # falls back to the first available model
    fallback_models: list[str] = []  # tried in order when the requested model fails
    llm_timeout_seconds: float = 60.0  # per http call to a provider
    llm_idle_timeout_seconds: float = 60.0  # max gap between two chunks (0 turns it off)
    llm_total_timeout_seconds: float = 300.0  # whole request incl. retries (0 turns it off)
    llm_max_retries: int = 2
    llm_retry_base_delay: float = 0.5
    llm_retry_max_delay: float = 8.0
    circuit_breaker_threshold: int = 5
    circuit_breaker_cooldown_seconds: float = 30.0

    # auto router: "auto" picks between a cheap and a strong model per prompt
    router_simple_model: str | None = None  # defaults to the default model
    router_complex_model: str | None = None  # defaults to the simple model
    router_threshold: int = 3
    router_long_prompt_chars: int = 800
    router_very_long_prompt_chars: int = 3000
    router_long_history_messages: int = 12
    router_keywords: list[str] = [
        "explain why",
        "step by step",
        "prove",
        "analyze",
        "analyse",
        "compare",
        "trade-off",
        "tradeoff",
        "design",
        "architecture",
        "debug",
        "optimize",
        "algorithm",
        "complexity",
        "refactor",
    ]

    # per-user daily quotas, reset at midnight utc (0 means unlimited)
    daily_request_quota: int = 200
    daily_token_quota: int = 200_000

    # chat
    system_prompt: str = "You are Sage, a helpful and concise AI assistant."
    max_history_messages: int = 40

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
