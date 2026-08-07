from pathlib import Path
from loguru import logger

from pgvector import Vector
from contextlib import closing

from src.common.db import get_connection
from src.common.embeddings import get_embedding_model
from src.common.utils import load_sql_query
from src.common.config import get_postgres_config


QUERIES_DIR = Path(__file__).parent / "queries"
TOP_K = 5


def retrieve(query: str) -> list[tuple]:
    # load the embedding model
    emb_model = get_embedding_model()                   

    # get the embedding for the query
    query_emb = emb_model.encode(query).tolist()

    # convert to pgvector type
    query_emb = Vector(query_emb)

    # load sql query to perform vector search
    vector_search_query = load_sql_query("vector_search.sql", QUERIES_DIR)

    # load postgres config
    db_config = get_postgres_config()

    # perform vector search
    with closing(get_connection(db_config)) as conn:
        with conn.cursor() as cur:
            cur.execute(vector_search_query, (query_emb, query_emb, TOP_K))
            top_k_candidates = cur.fetchall()

    logger.info("Vector search complete!")

    return top_k_candidates


if __name__ == "__main__":
    top_k_candidates = retrieve("My honda smells")

    for candidate in top_k_candidates:
        source, id, vehicle_tag, text, cosine_sim = candidate
        logger.debug(f"Source: {source}")
        logger.debug(f"ID: {id}")
        logger.debug(f"Vehicle Tag: {vehicle_tag}")
        logger.debug(f"Text: {text}")
        logger.debug(f"Cosine Similarity: {cosine_sim:.2f}")
        logger.debug("-" * 50)