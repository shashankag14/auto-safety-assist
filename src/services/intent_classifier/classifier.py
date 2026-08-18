from enum import StrEnum
from typing import Annotated

from fastapi import FastAPI, HTTPException, status
from loguru import logger

# openai imports
from openai import OpenAI, OpenAIError

# api service
from pydantic import BaseModel, Field

from src.common.config import AvailableModels, get_classifier_config

DEFAULT_MODEL = AvailableModels.GPT_4O_MINI

cfg = get_classifier_config()

client = OpenAI(api_key=cfg.openai_api_key)

classifier_api = FastAPI(title="Intent Classifier", description="Classify the intent of a query", version="0.1.0")


def _get_default_model() -> AvailableModels:
    try:
        return AvailableModels(cfg.model)
    except ValueError:
        logger.warning(
            f"OPENAI_MODEL='{cfg.model}' is not a supported classifier model "
            f"({[m.value for m in AvailableModels]}). Falling back to '{DEFAULT_MODEL.value}'."
        )
        return DEFAULT_MODEL


class Intent(StrEnum):
    """
    Defines the intents that can be classified by the intent classification model.
    """
    RECALL_LOOKUP = "recall_lookup"
    COMPLAINT_SEARCH = "complaint_search"
    GENERAL_QUESTION = "general_question"


class ClassifyIntentResponse(BaseModel):
    """
    Defines the structure of the intent classification result by the intent classification model.
    """
    # for structured output
    intent: Intent


class ClassifyIntentRequest(BaseModel):
    """
    Defines the request body for the classify_intent endpoint.
    """
    query: Annotated[str, Field(description="The query to classify", min_length=10, max_length=300)]
    model: Annotated[AvailableModels, Field(description="The model to use for classification")] = _get_default_model()


class HealthResponse(BaseModel):
    status: str


@classifier_api.post(path="/classify",
                    response_model=ClassifyIntentResponse,
                    summary="Classify the intent of a query",
                    response_description="The intent of the query. " \
                    "One of the following: RECALL_LOOKUP, COMPLAINT_SEARCH, GENERAL_QUESTION",
                    responses={
                        status.HTTP_500_INTERNAL_SERVER_ERROR: {
                            "description": "Failed to parse the intent classification response from the model",
                            "content": {"application/json": {"example": {"detail": "Failed to parse intent"}}},
                        },
                    })
@logger.catch(reraise=True)
def classify_intent(req: ClassifyIntentRequest) -> ClassifyIntentResponse:
    """
    Classify the intent of a query.

    - **req**: The query to classify. Must be between 10 and 300 characters.
    - **model**: The model to use for classification. Must be one of the following: GPT_4O_MINI, GPT_4O, GPT_4_1_MINI.
    """
    query = req.query

    try:
        # parse the intent
        response = client.responses.parse(
            model=req.model,
            instructions=cfg.instructions,
            input=query,
            text_format=ClassifyIntentResponse,
        )
    except OpenAIError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Failed to parse intent") from e

    # Check if output_parsed is None before accessing its attributes
    if response and response.output_parsed:
        return response.output_parsed

    else:
        logger.warning(f"Failed to parse intent for query: '{query}'. Falling back to GENERAL_QUESTION.")
        return ClassifyIntentResponse(intent=Intent.GENERAL_QUESTION)


@classifier_api.get(path="/healthz",
                    summary="Checks if the OpenAI client is constructed successfully.",
                    response_model=HealthResponse,
                    responses={
                        status.HTTP_500_INTERNAL_SERVER_ERROR: {
                            "description": "Failed to construct the OpenAI client",
                            "content": {
                                "application/json": {"example": {"detail": "Failed to construct the OpenAI client"}}
                            },
                        },
                    })
def healthz() -> HealthResponse:
    """
    Health check endpoint.
    """
    return HealthResponse(status="ok")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(classifier_api, host=cfg.host, port=cfg.port)