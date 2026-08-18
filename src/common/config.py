import os
from dataclasses import dataclass
from enum import StrEnum

from dotenv import load_dotenv

load_dotenv()


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class PostgresConfig:
    user: str | None
    password: str | None
    host: str
    port: str
    database: str


def get_postgres_config() -> PostgresConfig:
    return PostgresConfig(
        user=os.environ.get("POSTGRES_USER"),
        password=os.environ.get("POSTGRES_PASSWORD"),
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=os.environ.get("POSTGRES_PORT", "5432"),
        database=os.environ.get("DATABASE_NAME", "nhtsa"),
    )

class AvailableModels(StrEnum):
    """
    Defines the set of OpenAI models allowed for intent classification.
    """
    GPT_4O_MINI = "gpt-4o-mini"
    GPT_4_1_MINI = "gpt-4.1-mini"


@dataclass(frozen=True)
class ClassifierConfig:
    host: str
    port: int
    openai_api_key: str
    model: str
    instructions: str


CLASSIFIER_INSTRUCTIONS = """You are an intent classifier for a vehicle safety assistant.
Classify the user's question into exactly one of these categories:

- recall_lookup: the user is asking about an official recall for a vehicle (e.g. "is there a recall
  on my 2019 CR-V", "what does recall 21V123 fix").
- complaint_search: the user is asking about owner-reported problems/complaints for a vehicle that
  are not a specific recall (e.g. "have people complained about transmission issues in the F-150").
- general_question: anything else (greetings, unrelated questions, or questions too vague to route).
"""

def get_classifier_config() -> ClassifierConfig:
    return ClassifierConfig(
        host=os.environ.get("SERVICE_HOST", "localhost"),
        port=int(os.environ.get("CLASSIFIER_SERVICE_PORT", "8000")),
        openai_api_key=_require_env("OPENAI_API_KEY"),
        model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        instructions=CLASSIFIER_INSTRUCTIONS,
    )


@dataclass(frozen=True)
class RetrieverConfig:
    host: str
    port: int
    top_k: int = 5


def get_retriever_config() -> RetrieverConfig:
    return RetrieverConfig(
        host=os.environ.get("SERVICE_HOST", "localhost"),
        port=int(os.environ.get("RETRIEVER_SERVICE_PORT", "8001")),
        top_k=int(os.environ.get("TOP_K", "5")),
    )


@dataclass(frozen=True)
class ResponseGeneratorConfig:
    host: str
    port: int
    openai_api_key: str
    model: str
    instructions: str

RESPONSE_GENERATOR_INSTRUCTIONS = """You are a vehicle safety assistant. Answer the user's question using ONLY the
provided context of NHTSA recalls and owner complaints. Cite the source (recall or complaint) and
its ID for any claim you make. If the context does not contain enough information to answer,
say so instead of guessing.
"""

def get_response_generator_config() -> ResponseGeneratorConfig:
    return ResponseGeneratorConfig(
        host=os.environ.get("SERVICE_HOST", "localhost"),
        port=int(os.environ.get("RESPONSE_GENERATOR_SERVICE_PORT", "8002")),
        openai_api_key=_require_env("OPENAI_API_KEY"),
        model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        instructions=RESPONSE_GENERATOR_INSTRUCTIONS,
    )


# Data ingestion config
TARGET_VEHICLES = [
    {"make": "bmw", "model": "x5", "modelYear": 2018},
    {"make": "toyota", "model": "camry", "modelYear": 2022},
    {"make": "honda", "model": "cr-v", "modelYear": 2022},
]
