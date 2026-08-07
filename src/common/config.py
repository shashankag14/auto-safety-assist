import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


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


TARGET_VEHICLES = [
    {"make": "bmw", "model": "x5", "modelYear": 2018},
    {"make": "toyota", "model": "camry", "modelYear": 2022},
    {"make": "honda", "model": "cr-v", "modelYear": 2022},
]

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

CLASSIFIER_INSTRUCTIONS = """You are an intent classifier for a vehicle safety assistant.
Classify the user's question into exactly one of these categories:

- recall_lookup: the user is asking about an official recall for a vehicle (e.g. "is there a recall on my 2019 CR-V", "what does recall 21V123 fix").
- complaint_search: the user is asking about owner-reported problems/complaints for a vehicle that are not a specific recall (e.g. "have people complained about transmission issues in the F-150").
- general_question: anything else (greetings, unrelated questions, or questions too vague to route).
"""

RESPONSE_INSTRUCTIONS = """You are a vehicle safety assistant. Answer the user's question using ONLY the
provided context of NHTSA recalls and owner complaints. Cite the source (recall or complaint) and
its ID for any claim you make. If the context does not contain enough information to answer,
say so instead of guessing.
"""
