from pathlib import Path

from pydantic_settings import BaseSettings

VIDEO_JSON_PATH = Path("artifacts/video_resources.json")
SCHEMA_DIR = Path("artifacts/events_schema")
ATTRIBUTES_JSON_PATH = Path("artifacts/attributes.json")


class Settings(BaseSettings):
    LLM_MODEL: str
    LLM_TEMPERATURE: float = 0
    LLM_TIMEOUT: int = 120
    OPENAI_API_KEY: str
    LLM_BASE_URL: str

    class Config:
        env_file = ".env"


settings = Settings()
