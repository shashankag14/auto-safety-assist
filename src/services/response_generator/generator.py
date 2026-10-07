from fastapi import FastAPI, HTTPException, status

# logging
from loguru import logger

# openai imports
from openai import OpenAI, OpenAIError

# local packages
from src.common.config import get_response_generator_config
from src.common.schemas import Candidates
from src.services.response_generator.schemas import (
    AnswerRequest,
    GenerateResponse,
    GenerateResponseRequest,
    HealthResponse,
)

cfg = get_response_generator_config()

client = OpenAI(api_key=cfg.openai_api_key)

generator_api = FastAPI(title="Response Generator", description="Generate a response to a query", version="0.1.0")


def build_context(candidates: list[Candidates]) -> str:
    """
    Build the context in string format to pass into the OpenAI model as an input text.
    """
    lines = []
    for candidate in candidates:
        lines.append(f"[{candidate.source} {candidate.external_id} | {candidate.vehicle_tag}]\n{candidate.text}")
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
            temperature=cfg.temperature,
        )
    except OpenAIError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Failed to generate response") from e

    return GenerateResponse(response=response.output_text)


@generator_api.post(path="/answer",
                    response_model=GenerateResponse,
                    summary="Answer a query without retrieved candidates",
                    response_description="The generated response",
                    responses={
                        status.HTTP_500_INTERNAL_SERVER_ERROR: {
                            "description": "Failed to generate the response",
                            "content": {"application/json": {"example": {"detail": "Failed to generate response"}}},
                        },
                    })
@logger.catch(reraise=True)
def answer(req: AnswerRequest) -> GenerateResponse:
    """
    Answer a query from general knowledge, for general questions or when no matching
    recalls/complaints were retrieved. Never cites specific recall or complaint IDs.

    - **req**: The query to answer. Must be between 10 and 300 characters.
    """
    try:
        response = client.responses.create(
            model=req.model,
            instructions=cfg.general_instructions,
            input=req.query,
            temperature=cfg.temperature,
        )
    except OpenAIError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Failed to generate response") from e

    return GenerateResponse(response=response.output_text)


@generator_api.get(path="/healthz",
                    summary="Checks if the OpenAI client is constructed successfully.",
                    response_model=HealthResponse,
                    responses={
                        status.HTTP_500_INTERNAL_SERVER_ERROR: {
                            "description": "Failed to construct the OpenAI client",
                            "content": {"application/json": {"example": 
                                                             {"detail": "Failed to construct the OpenAI client"}}}
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
