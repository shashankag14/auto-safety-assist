from typing import Annotated

from pydantic import BaseModel, Field

from src.common.config import AvailableModels, get_default_openai_model
from src.common.schemas import Candidates


class GenerateResponseRequest(BaseModel):
    """
    Defines the request body for the generate_response endpoint.
    """
    query: Annotated[str, Field(description="The query to generate a response for", min_length=10, max_length=300)]
    candidates: Annotated[list[Candidates], Field(description="The candidates to use for response generation",
                                                  min_length=1, max_length=10)]
    model: Annotated[
        AvailableModels, Field(description="The model to use for response generation")
    ] = get_default_openai_model()


class GenerateResponse(BaseModel):
    """
    Defines the response body for the generate_response endpoint.
    """
    response: str


class HealthResponse(BaseModel):
    status: str
