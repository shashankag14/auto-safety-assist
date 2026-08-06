from embedding import generate_db
from utils import load_sql_query

import psycopg2
from pgvector import Vector
from pgvector.psycopg2 import register_vector
from contextlib import closing

from loguru import logger
from rag import rag_pipeline
from ingestion import ingest
from classifier import classify_intent, Intent


def run_ml_pipeline(query: str) -> None:
    # data ingestion
    logger.info("Starting ingestion...")
    ingest()

    # load embedding model
    logger.info("Generating database...")
    generate_db()

    # intent classification
    logger.info("Running intent classifier...")
    intent = classify_intent(query)
    # if general question recognized, then return
    if intent == Intent.GENERAL_QUESTION:
        logger.warning("General question detected, skipping RAG pipeline")
        return

    # RAG pipeline
    logger.info("Running RAG pipeline...")
    response = rag_pipeline(query)

    logger.success(f"Response: {response}")

if __name__ == "__main__":
    run_ml_pipeline("my honda fuel pump smells like shit")

