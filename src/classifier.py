import os
from enum import Enum

from dotenv import load_dotenv
from loguru import logger
from openai import OpenAI
from pydantic import BaseModel

load_dotenv()

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

DEFAULT_MODEL = os.environ.get("OPENAI_CLASSIFIER_MODEL", "gpt-4o-mini")

INSTRUCTIONS = """You are an intent classifier for a vehicle safety assistant.
Classify the user's question into exactly one of these categories:

- recall_lookup: the user is asking about an official recall for a vehicle (e.g. "is there a recall on my 2019 CR-V", "what does recall 21V123 fix").
- complaint_search: the user is asking about owner-reported problems/complaints for a vehicle that are not a specific recall (e.g. "have people complained about transmission issues in the F-150").
- general_question: anything else (greetings, unrelated questions, or questions too vague to route).
"""


class Intent(str, Enum):
    RECALL_LOOKUP = "recall_lookup"
    COMPLAINT_SEARCH = "complaint_search"
    GENERAL_QUESTION = "general_question"


class IntentClassification(BaseModel):
    # for structured output, we define a Pydantic model with a single field for the intent
    intent: Intent


def classify_intent(query: str, model: str = DEFAULT_MODEL) -> Intent:
    response = client.responses.parse(
        model=model,
        instructions=INSTRUCTIONS,
        input=query,
        text_format=IntentClassification,
    )

    return response.output_parsed.intent


def main():
    # samples queries to test the intent classifier
    queries = [
        "Is there a recall on my 2019 Honda CR-V for the fuel pump?",
        "Have other F-150 owners complained about the transmission slipping?",
        "What's the difference between a recall and a TSB?",
    ]

    for query in queries:
        intent = classify_intent(query)
        logger.info(f"'{query}' -> {intent}")


if __name__ == "__main__":
    main()
