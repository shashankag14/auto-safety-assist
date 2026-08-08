from pathlib import Path
from loguru import logger

# api service
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Annotated

# postgres and pgvector imports
from pgvector import Vector
from contextlib import closing

# local packages
from src.common.db import get_connection
from src.common.embeddings import get_embedding_model
from src.common.utils import load_sql_query
from src.common.config import get_postgres_config, get_retriever_config

# load retriever config parameters (api server, top_k etc)
cfg = get_retriever_config()

# load postgres config
db_config = get_postgres_config()

# load embedding model
emb_model = get_embedding_model()

QUERIES_DIR = Path(__file__).parent / "queries"
VECTOR_SEARCH_QUERY = load_sql_query("vector_search.sql", QUERIES_DIR)

retriever_api = FastAPI(title="Retreiver based on input query",
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
    candidates: Annotated[list[Candidates], Field(description="The candidates to use for response generation", min_length=1, max_length=10)]


@retriever_api.post(path="/retrieve",
                    summary="Provides the top-k matching recalls/complaints based on user input query.",
                    response_model=RetrieverResponse,
                    responses={
                        500: {
                            "description": "Failed to retrieve candidates",
                            "content": {"application/json": {"example": {"detail": "Failed to retrieve candidates"}}},
                        },
                    })
@logger.catch(reraise=True)
def retrieve(req: RetrieverRequest) -> RetrieverResponse:
    # get the embedding for the query
    try:
        query_emb = emb_model.encode(req.query).tolist()
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to create vector embedding of the input query.")

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
        raise HTTPException(status_code=404, detail="No matching recall/complaints found.")

    logger.info("Vector search complete!")

    # formulate the retrieved candidates as a defined pydantic BaseModel type class
    try:
        candidates = [
            Candidates(source=source, id=id, vehicle_tag=vehicle_tag, text=text, cosine_sim=cosine_sim)
            for source, id, vehicle_tag, text, cosine_sim in top_k_candidates
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to retrieve candidates. Error: {e}")

    return RetrieverResponse(candidates=candidates)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(retriever_api, host=cfg.host, port=cfg.port)