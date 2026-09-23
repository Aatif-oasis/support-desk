"""
Centralized application settings.
All configuration is environment-driven — never hardcode secrets or connection
strings elsewhere in the codebase. Every module imports `settings` from here.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    APP_NAME: str = "Chat Support"
    ENVIRONMENT: str = "development"  # development | staging | production
    DEBUG: bool = True

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://oasis_chatbot:oasis_chatbot@localhost:5432/oasis_chatbot"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT / Auth
    JWT_SECRET_KEY: str = "CHANGE_ME_IN_PRODUCTION"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # What the visitor sees the moment an agent picks up their chat.
    # {agent} is replaced with the agent's name. Set to an empty string to
    # send nothing — some teams prefer to type their own opener.
    AGENT_JOIN_GREETING: str = "Hi, this is {agent}. I'll help you with this."

    # Set to true only when the app sits behind a reverse proxy you
    # control (nginx, a load balancer). Then X-Forwarded-For carries the
    # real client address. With no proxy in front, leave it false —
    # otherwise anyone can send that header and claim any address they
    # like, which would defeat the IP restriction entirely.
    TRUST_FORWARDED_FOR: bool = False

    # Pre-chat verification. Off by default so existing embeds keep
    # working after an upgrade; turn it on per deployment.
    CAPTCHA_ENABLED: bool = False

    # Organization signup
    # Empty = anyone who can reach the API may create an organization. That
    # is fine on a laptop and wrong on a public server, so any non-empty
    # value here locks /auth/register behind the X-Setup-Key header.
    SIGNUP_SETUP_KEY: str = ""

    # API Keys
    API_KEY_HEADER_NAME: str = "X-API-Key"

    # CORS
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000"]

    # Webhooks
    # Default is inline delivery, which is what the existing test suite
    # asserts against. Set WEBHOOK_ASYNC_DELIVERY=true in any real
    # deployment so a slow CRM receiver can't hold up a customer's message.
    WEBHOOK_ASYNC_DELIVERY: bool = False
    WEBHOOK_MAX_ATTEMPTS: int = 3

    # File uploads (Module 7)
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE_BYTES: int = 20 * 1024 * 1024  # 20 MB


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if not settings.DEBUG and settings.JWT_SECRET_KEY == "CHANGE_ME_IN_PRODUCTION":
        raise RuntimeError(
            "Refusing to start: JWT_SECRET_KEY is still the default value while "
            "ENVIRONMENT is not development/DEBUG. Set a real secret before "
            "running anywhere near production traffic — every issued token is "
            "forgeable otherwise."
        )
    return settings


settings = get_settings()
