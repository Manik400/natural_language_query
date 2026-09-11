from langchain_openai import ChatOpenAI

from config import settings


def get_llm() -> ChatOpenAI:
    llm_instance = ChatOpenAI(
        model=settings.LLM_MODEL,
        temperature=settings.LLM_TEMPERATURE,
        base_url=settings.LLM_BASE_URL,
        timeout=settings.LLM_TIMEOUT,
        api_key=settings.OPENAI_API_KEY,
    )
    return llm_instance
