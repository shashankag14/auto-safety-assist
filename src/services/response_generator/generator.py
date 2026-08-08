# logging
from loguru import logger

# openai imports
from openai import OpenAI, OpenAIError

# api service
from pydantic import BaseModel, Field
from typing import Annotated
from fastapi import FastAPI, HTTPException, status

# local packages
from src.common.config import get_response_generator_config, AvailableModels


DEFAULT_MODEL = AvailableModels.GPT_4O_MINI

cfg = get_response_generator_config()

client = OpenAI(api_key=cfg.openai_api_key)

generator_api = FastAPI(title="Response Generator", description="Generate a response to a query", version="0.1.0")


def _get_default_model() -> AvailableModels:
    try:
        return AvailableModels(cfg.model)
    except ValueError:
        logger.warning(f"OPENAI_MODEL='{cfg.model}' is not a supported model ({[m.value for m in AvailableModels]}). Falling back to '{DEFAULT_MODEL.value}'")
        return DEFAULT_MODEL


class Candidates(BaseModel):
    """
    Defines the schema for the candidates provided as an input to the response generator.
    Each candidate should have the following fields listed below.

    (Refer the SQL database table definitions as a reference to declare the datatypes)
    """
    source: Annotated[str, Field(description="The source of the candidate")]
    id: Annotated[int, Field(description="The ID of the candidate")]
    vehicle_tag: Annotated[str, Field(description="The vehicle tag of the candidate")]
    text: Annotated[str, Field(description="The text of the candidate")]
    cosine_sim: Annotated[float, Field(description="The cosine similarity of the candidate", gt=0, le=1)]


class GenerateResponseRequest(BaseModel):
    """
    Defines the request body for the generate_response endpoint.
    """
    query: Annotated[str, Field(description="The query to generate a response for", min_length=10, max_length=300)]
    candidates: Annotated[list[Candidates], Field(description="The candidates to use for response generation", min_length=1, max_length=10)]
    model: Annotated[AvailableModels, Field(description="The model to use for response generation")] = _get_default_model()


class GenerateResponse(BaseModel):
    """
    Defines the response body for the generate_response endpoint.
    """
    response: str


class HealthResponse(BaseModel):
    status: str


def build_context(candidates: list[Candidates]) -> str:
    """
    Build the context in string format to pass into the OpenAI model as an input text.
    """
    lines = []
    for candidate in candidates:
        lines.append(f"[{candidate.source} {candidate.id} | {candidate.vehicle_tag}]\n{candidate.text}")
    return "\n\n".join(lines)


@generator_api.post(path="/generate",
                    response_model=GenerateResponse,
                    summary="Generate a response to a query",
                    response_description="The generated response",
                    responses={
                        status.HTTP_500_INTERNAL_SERVER_ERROR: {
                            "description": "Failed to generate the response",
                            "content": {"application/json": {"example": {"detail": "Failed to generate response"}}},
                        },
                    })
@logger.catch(reraise=True)
def generate_response(req: GenerateResponseRequest) -> GenerateResponse:
    """
    Generate a response to a query.

    - **req**: The query to generate a response for. Must be between 10 and 300 characters.
    """
    query = req.query
    candidates = req.candidates
    model = req.model

    # build the context in string format
    context = build_context(candidates)

    input_text = f"Context:\n{context}\n\nQuestion: {query}"

    try:
        response = client.responses.create(
            model=model,
            instructions=cfg.instructions,
            input=input_text,
        )
    except OpenAIError:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Failed to generate response")

    return GenerateResponse(response=response.output_text)


@generator_api.get(path="/healthz",
                    summary="Checks if the OpenAI client is constructed successfully.",
                    response_model=HealthResponse,
                    responses={
                        status.HTTP_500_INTERNAL_SERVER_ERROR: {
                            "description": "Failed to construct the OpenAI client",
                            "content": {"application/json": {"example": {"detail": "Failed to construct the OpenAI client"}}}
                        },
                    })
def healthz() -> HealthResponse:
    """
    Health check endpoint.
    """
    if client is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Failed to construct the OpenAI client")
    return HealthResponse(status="ok")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(generator_api, host=cfg.host, port=cfg.port)
