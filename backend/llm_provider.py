"""
llm_provider.py

A single factory function that returns the right LLM based on env vars.
"""

import os
from dotenv import load_dotenv

load_dotenv()


def get_llm():
    """
    Returns a LangChain-compatible LLM based on LLM_PROVIDER env var.

    Usage:
        llm = get_llm()
        llm_with_tools = llm.bind_tools(tools)  # standard LangChain API
    """
    provider = os.getenv("LLM_PROVIDER", "ollama")

    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model="gpt-4o",
            api_key=os.getenv("OPENAI_API_KEY"),
            temperature=0,   # 0 = deterministic, we want consistent decisions
        )

    elif provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=os.getenv("OLLAMA_MODEL", "qwen3:14b"),
            temperature=0,
            base_url="http://localhost:11434",
        )

    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER: '{provider}'. "
            "Set LLM_PROVIDER=openai or LLM_PROVIDER=ollama in your .env"
        )
