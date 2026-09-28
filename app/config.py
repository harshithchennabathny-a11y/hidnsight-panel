"""Central config + client factories. Every other module imports from here
so keys/URLs live in exactly one place."""
import os
from functools import lru_cache
from dotenv import load_dotenv

load_dotenv()


class ConfigError(RuntimeError):
    """Raised instead of silently falling back to mock data (Invariant 3.6)."""


def _require(name: str) -> str:
    val = os.getenv(name, "").strip()
    if not val:
        raise ConfigError(f"Missing required env var {name}. Set it in .env")
    return val


USE_MOCKS = os.getenv("PANEL_USE_MOCKS", "false").lower() == "true"
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")


@lru_cache(maxsize=1)
def hindsight_client():
    from hindsight_client import Hindsight
    return Hindsight(
        base_url=os.getenv("HINDSIGHT_BASE_URL", "https://api.hindsight.vectorize.io"),
        api_key=_require("HINDSIGHT_API_KEY"),
        timeout=60.0,
    )


@lru_cache(maxsize=1)
def groq_client():
    from groq import Groq
    return Groq(api_key=_require("GROQ_API_KEY"), timeout=45.0, max_retries=2)
