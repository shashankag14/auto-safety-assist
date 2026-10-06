from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field

from src.common.config import AvailableModels, get_default_openai_model


class Intent(StrEnum):
    """
    Defines the intents that can be classified by the intent classification model.
    """
    RECALL_LOOKUP = "recall_lookup"
    COMPLAINT_SEARCH = "complaint_search"
    GENERAL_QUESTION = "general_question"


class IntentOutput(BaseModel):
    """
    Defines the structured output the intent classification model must return.
    """
    intent: Intent


class ClassifyIntentResponse(BaseModel):
    """
    Defines the response body for the classify_intent endpoint.
    """
    intent: Annotated[Intent | None, Field(description="The classified intent, or null if the model output "
                                                       "could not be parsed")]


class ClassifyIntentRequest(BaseModel):
    """
    Defines the request body for the classify_intent endpoint.
    """
    query: Annotated[str, Field(description="The query to classify", min_length=10, max_length=300)]
    model: Annotated[AvailableModels, Field(description="The model to use for classification")] = \
        get_default_openai_model()


class HealthResponse(BaseModel):
    status: str
