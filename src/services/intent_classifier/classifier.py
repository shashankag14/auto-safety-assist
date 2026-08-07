from enum import Enum
from loguru import logger
from openai import OpenAI
from pydantic import BaseModel, Field
from typing import Annotated
from fastapi import FastAPI, HTTPException

from src.common.config import OPENAI_API_KEY, OPENAI_MODEL, CLASSIFIER_INSTRUCTIONS


client = OpenAI(api_key=OPENAI_API_KEY)
api = FastAPI()


class ClassifierModel(str, Enum):
    """
    Defines the set of OpenAI models allowed for intent classification.
    """
    GPT_4O_MINI = "gpt-4o-mini"
    GPT_4O = "gpt-4o"
    GPT_4_1_MINI = "gpt-4.1-mini"


DEFAULT_CLASSIFIER_MODEL = ClassifierModel.GPT_4O_MINI


def _get_default_model() -> ClassifierModel:
    try:
        return ClassifierModel(OPENAI_MODEL)
    except ValueError:
        logger.warning(
            f"OPENAI_MODEL='{OPENAI_MODEL}' is not a supported classifier model "
            f"({[m.value for m in ClassifierModel]}). Falling back to '{DEFAULT_CLASSIFIER_MODEL.value}'."
        )
        return DEFAULT_CLASSIFIER_MODEL

class Intent(str, Enum):
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
    model: Annotated[ClassifierModel, Field(description="The model to use for classification")] = _get_default_model()


@api.post(path="/classify",
          response_model=ClassifyIntentResponse,
          summary="Classify the intent of a query",
          response_description="The intent of the query. " \
          "One of the following: RECALL_LOOKUP, COMPLAINT_SEARCH, GENERAL_QUESTION",
          responses={
              500: {
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
            instructions=CLASSIFIER_INSTRUCTIONS,
            input=query,
            text_format=ClassifyIntentResponse,
        )
    except:
        raise HTTPException(status_code=500, detail="Failed to parse intent")

    # Check if output_parsed is None before accessing its attributes
    if response and response.output_parsed:
        return response.output_parsed

    else:
        logger.warning(f"Failed to parse intent for query: '{query}'. Falling back to GENERAL_QUESTION.")
        return ClassifyIntentResponse(intent=Intent.GENERAL_QUESTION)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(api, host="0.0.0.0", port=8000)