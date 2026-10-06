from fastapi import FastAPI, HTTPException, status
from loguru import logger

# openai imports
from openai import OpenAI, OpenAIError

from src.common.config import get_classifier_config
from src.services.intent_classifier.schemas import (
    ClassifyIntentRequest,
    ClassifyIntentResponse,
    HealthResponse,
    IntentOutput,
)

cfg = get_classifier_config()

client = OpenAI(api_key=cfg.openai_api_key)

classifier_api = FastAPI(title="Intent Classifier", description="Classify the intent of a query", version="0.1.0")


@classifier_api.post(path="/classify",
                    response_model=ClassifyIntentResponse,
                    summary="Classify the intent of a query",
                    response_description="The intent of the query. " \
                    "One of the following: RECALL_LOOKUP, COMPLAINT_SEARCH, GENERAL_QUESTION, " \
                    "or null if the model output could not be parsed",
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
            text_format=IntentOutput,
        )
    except OpenAIError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Failed to parse intent") from e

    # output_parsed is None when the model refuses or the output is truncated. Return null instead of
    # guessing an intent, so callers can choose a safe route and evals can count it separately.
    if response and response.output_parsed:
        return ClassifyIntentResponse(intent=response.output_parsed.intent)

    logger.warning(f"Failed to parse intent for query: '{query}'. Returning null intent.")
    return ClassifyIntentResponse(intent=None)


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