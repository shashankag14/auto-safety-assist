from enum import Enum
from loguru import logger
from openai import OpenAI
from pydantic import BaseModel

from src.common.config import OPENAI_API_KEY, OPENAI_MODEL, CLASSIFIER_INSTRUCTIONS


client = OpenAI(api_key=OPENAI_API_KEY)


class Intent(str, Enum):
    RECALL_LOOKUP = "recall_lookup"
    COMPLAINT_SEARCH = "complaint_search"
    GENERAL_QUESTION = "general_question"


class IntentClassification(BaseModel):
    # for structured output
    intent: Intent


def classify_intent(query: str, model: str = OPENAI_MODEL) -> Intent:
    response = client.responses.parse(
        model=model,
        instructions=CLASSIFIER_INSTRUCTIONS,
        input=query,
        text_format=IntentClassification,
    )

    # Check if output_parsed is None before accessing its attributes
    if response and response.output_parsed:
        return response.output_parsed.intent
    else:
        logger.warning(f"Failed to parse intent for query: '{query}'. Falling back to GENERAL_QUESTION.")
        return Intent.GENERAL_QUESTION
