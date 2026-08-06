import os
from loguru import logger

import psycopg2
from pgvector import Vector
from pgvector.psycopg2 import register_vector
from contextlib import closing

from openai import OpenAI

from dotenv import load_dotenv

from embedding import get_embedding_model
from utils import load_sql_query

load_dotenv()

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

DEFAULT_MODEL = os.environ.get("OPENAI_RAG_MODEL", "gpt-4o-mini")

INSTRUCTIONS = """You are a vehicle safety assistant. Answer the user's question using ONLY the
provided context of NHTSA recalls and owner complaints. Cite the source (recall or complaint) and
its ID for any claim you make. If the context does not contain enough information to answer,
say so instead of guessing.
"""


def build_context(results: list[tuple]) -> str:
    lines = []
    for source, id, vehicle_tag, text, cosine_sim in results:
        lines.append(f"[{source} {id} | {vehicle_tag}]\n{text}")
    return "\n\n".join(lines)


def generate_response(query: str, results: list[tuple], model: str = DEFAULT_MODEL) -> str:
    context = build_context(results)
    input_text = f"Context:\n{context}\n\nQuestion: {query}"

    response = client.responses.create(
        model=model,
        instructions=INSTRUCTIONS,
        input=input_text,
    )

    return response.output_text


def rag_pipeline(query: str) -> str:
    postgres_user = os.environ.get("POSTGRES_USER")
    postgres_password = os.environ.get("POSTGRES_PASSWORD")
    postgres_host = os.environ.get("POSTGRES_HOST", "localhost")
    postgres_port = os.environ.get("POSTGRES_PORT", "5432")

    database_name = os.environ.get("DATABASE_NAME") or "nhtsa"

    logger.debug(f"Query: {query}")
    logger.debug("-" * 50)

    # load the embedding model
    emb_model = get_embedding_model()                   

    # get the embedding for the query
    query_emb = emb_model.encode(query).tolist()

    # convert to pgvector type
    query_emb = Vector(query_emb)

    VECTOR_SEARCH_QUERY = load_sql_query("vector_search.sql")

    # perform vector search
    with closing(psycopg2.connect(dbname=database_name, user=postgres_user, password=postgres_password,
                            host=postgres_host, port=postgres_port)) as conn:
        with conn:
            register_vector(conn)

            with conn.cursor() as cur:
                cur.execute(VECTOR_SEARCH_QUERY, (query_emb, query_emb, 5))
                results = cur.fetchall()

                # TODO: use a DEBUG flag to enable this block
                for row in results:
                    source, id, vehicle_tag, text, cosine_sim = row
                    logger.debug(f"Source: {source}")
                    logger.debug(f"ID: {id}")
                    logger.debug(f"Vehicle Tag: {vehicle_tag}")
                    logger.debug(f"Text: {text}")
                    logger.debug(f"Cosine Similarity: {cosine_sim:.2f}")
                    logger.debug("-" * 50)

    logger.info("Vector search complete!")

    # Generate LLM response based on top-k retrievals
    logger.info("Starting LLM call...")
    answer = generate_response(query, results)

    logger.info(f"Answer: {answer}")#

    return answer


if __name__ == "__main__":
    rag_pipeline("My honda smells")