from contextlib import closing
from pathlib import Path
from typing import Annotated

# api service
from fastapi import FastAPI, HTTPException, status
from loguru import logger

# postgres and pgvector imports
from pgvector import Vector
from pydantic import BaseModel, Field

from src.common.config import get_postgres_config, get_retriever_config

# local packages
from src.common.db import get_connection
from src.common.embeddings import get_embedding_model
from src.common.utils import load_sql_query

# load retriever config parameters (api server, top_k etc)
cfg = get_retriever_config()

# load postgres config
db_config = get_postgres_config()

# load embedding model
emb_model = get_embedding_model()

QUERIES_DIR = Path(__file__).parent / "queries"
VECTOR_SEARCH_QUERY = load_sql_query("vector_search.sql", QUERIES_DIR)

retriever_api = FastAPI(title="Retreiver",
                        version="0.1.0",
                        summary="Retrives top matching candidates from recall/complaints against the user input query.")


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


@retriever_api.post(path="/retrieve",
                    summary="Provides the top-k matching recalls/complaints based on user input query.",
                    response_model=RetrieverResponse,
                    responses={
                        status.HTTP_404_NOT_FOUND: {
                            "description": "No matching recalls/complaints found",
                            "content": {"application/json": {"example":
                                                             {"detail": "No matching recall/complaints found."}}},
                        },
                        status.HTTP_500_INTERNAL_SERVER_ERROR: {
                            "description": "Failed to embed the query or retrieve candidates",
                            "content": {"application/json": {"example": {"detail": "Failed to retrieve candidates"}}},
                        },
                    })
@logger.catch(reraise=True)
def retrieve(req: RetrieverRequest) -> RetrieverResponse:
    """
    Embeds the input query and runs a cosine-similarity search over the
    recalls/complaints vector store, returning the top-k matches.
    """
    # get the embedding for the query
    try:
        query_emb = emb_model.encode(req.query).tolist()
    except Exception as e:
        logger.error(f"Failed to create vector embedding of the input query. Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create vector embedding of the input query.") from e

    # convert to pgvector type
    query_emb = Vector(query_emb)

    # perform vector search
    with closing(get_connection(db_config)) as conn:
        with conn.cursor() as cur:
            cur.execute(VECTOR_SEARCH_QUERY, (query_emb, query_emb, cfg.top_k))
            top_k_candidates = cur.fetchall()

    # Check if there are any top-k retrieved candidates available
    if not top_k_candidates:
        # TODO: fallback to GENERAL_QUESTION intent route
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="No matching recall/complaints found.")

    logger.info("Vector search complete!")

    # formulate the retrieved candidates as a defined pydantic BaseModel type class
    try:
        candidates = [
            Candidates(source=source, id=id, vehicle_tag=vehicle_tag, text=text, cosine_sim=round(cosine_sim, 2))
            for source, id, vehicle_tag, text, cosine_sim in top_k_candidates
        ]
    except Exception as e:
        logger.error(f"Failed to retrieve candidates. Error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Failed to retrieve candidates.") from e

    return RetrieverResponse(candidates=candidates)


@retriever_api.get(path="/database_details",
                summary="Provides the number of recalls and complaints in the database.",
                response_model=DatabaseDetails,
                responses={
                        status.HTTP_500_INTERNAL_SERVER_ERROR: {
                            "description": "Failed to fetch database details",
                            "content": {"application/json": 
                                        {"example": {"detail": "Failed to fetch database details"}}},
                        },
                })
@logger.catch(reraise=True)
def get_database_details() -> DatabaseDetails:
    """
    Fetches the number of recalls and complaints in the database.
    """
    try:
        with closing(get_connection(db_config)) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM vehicle_recalls")
                recalls_count = cur.fetchone()

                cur.execute("SELECT COUNT(*) FROM vehicle_complaints")
                complaints_count = cur.fetchone()

        if recalls_count is None or complaints_count is None:
            raise ValueError("COUNT(*) query returned no rows")

    except Exception as e:
        logger.error(f"Failed to retrieve database details. Error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Failed to retrieve database details.") from e

    return DatabaseDetails(recalls_count=recalls_count[0], complaints_count=complaints_count[0])


@retriever_api.get(path="/healthz",
                summary="Checks if the service can reach to the postgres server.",
                response_model=HealthResponse,
                responses={
                    503: {
                        "description": "Failed to connect to database.",
                        "content": {"application/json": {"example": {"detail": "Failed to connect to database."}}},
                        },
                })
def healthz() -> HealthResponse:
    """Health check endpoint to check if the service can reach to the postgres server.

    Returns:
        HealthResponse: A schema containing the status of the service.
    """
    # check if service can reach to the postgres server
    try:
        with closing(get_connection(db_config)) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
    except Exception as e:
        logger.error(f"Failed to connect to database. Error: {e}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Failed to connect to database.") from e

    return HealthResponse(status="ok")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(retriever_api, host=cfg.host, port=cfg.port)