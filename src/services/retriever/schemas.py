from typing import Annotated

from pydantic import BaseModel, Field

from src.common.schemas import Candidates


class RetrieverRequest(BaseModel):
    """
    Defines the request body for the retriever endpoint.
    """
    query: Annotated[str, Field(description="The query to retrieve candidates for", min_length=10, max_length=300)]


class RetrieverResponse(BaseModel):
    """
    Defines the response body for the retriever endpoint.
    """
    candidates: Annotated[list[Candidates],
                          Field(description="The candidates to use for response generation",
                                min_length=1, max_length=10)]


class HealthResponse(BaseModel):
    status: str


class DatabaseDetails(BaseModel):
    """
    Defines the response body for the database_details endpoint.
    """
    recalls_count: Annotated[int, Field(description="The number of recalls in the database")]
    complaints_count: Annotated[int, Field(description="The number of complaints in the database")]
