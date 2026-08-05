import os
from loguru import logger

import psycopg2
from pgvector import Vector
from pgvector.psycopg2 import register_vector
from contextlib import closing

from dotenv import load_dotenv

from embedding import get_embedding_model, load_sql_query

load_dotenv()


def main():
    query = "Is there a recall on my 2019 Honda CR-V for the fuel pump?"
    logger.debug(f"Query: {query}")
    logger.debug("-" * 50)

    # load the embedding model
    emb_model = get_embedding_model()                   

    # get the embedding for the query
    query_emb = emb_model.encode(query).tolist()

    # convert to pgvector type
    query_emb = Vector(query_emb)

    postgres_user = os.environ.get("POSTGRES_USER")
    postgres_password = os.environ.get("POSTGRES_PASSWORD")
    postgres_host = os.environ.get("POSTGRES_HOST", "localhost")
    postgres_port = os.environ.get("POSTGRES_PORT", "5432")

    database_name = os.environ.get("DATABASE_NAME") or "nhtsa"

    VECTOR_SEARCH_QUERY = load_sql_query("vector_search.sql")

    with closing(psycopg2.connect(dbname=database_name, user=postgres_user, password=postgres_password,
                            host=postgres_host, port=postgres_port)) as conn:
        with conn:
            register_vector(conn)

            with conn.cursor() as cur:
                cur.execute(VECTOR_SEARCH_QUERY, (query_emb, query_emb, 5))
                results = cur.fetchall()

                for row in results:
                    source, id, vehicle_tag, text, cosine_sim = row
                    logger.debug(f"Source: {source}")
                    logger.debug(f"ID: {id}")
                    logger.debug(f"Vehicle Tag: {vehicle_tag}")
                    logger.debug(f"Text: {text}")
                    logger.debug(f"Cosine Similarity: {cosine_sim:.2f}")
                    logger.debug("-" * 50)


if __name__ == "__main__":
    main()