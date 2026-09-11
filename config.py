from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Absolute paths so the app works no matter which directory it is started from
# (Streamlit Cloud, uvicorn, scripts).
BASE_DIR = Path(__file__).resolve().parent

VIDEO_JSON_PATH = BASE_DIR / "artifacts" / "video_resources.json"
SCHEMA_DIR = BASE_DIR / "artifacts" / "events_schema"
ATTRIBUTES_JSON_PATH = BASE_DIR / "artifacts" / "attributes.json"
DUMMY_EVENTS_PATH = BASE_DIR / "data" / "dummy_events.jsonl"


class Settings(BaseSettings):
    """LLM settings, read from environment variables or a local .env file.

    All fields are optional so the app can start without an LLM key; in that
    case the UI falls back to the rule-based offline parser.
    """

    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore")

    LLM_MODEL: str = ""
    LLM_TEMPERATURE: float = 0
    LLM_TIMEOUT: int = 120
    OPENAI_API_KEY: str = ""
    LLM_BASE_URL: str = ""  # empty → OpenAI's default endpoint

    @property
    def llm_configured(self) -> bool:
        return bool(self.OPENAI_API_KEY and self.LLM_MODEL)


settings = Settings()
