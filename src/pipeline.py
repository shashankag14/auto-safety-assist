from loguru import logger

from src.ingestion.build_index import build_index
from src.ingestion.ingestion import ingest
from src.services.intent_classifier.classifier import classify_intent
from src.services.intent_classifier.schemas import ClassifyIntentRequest, Intent
from src.services.response_generator.generator import generate_response
from src.services.response_generator.schemas import GenerateResponseRequest
from src.services.retriever.retriever import retrieve
from src.services.retriever.schemas import RetrieverRequest


def run_pipeline(query: str) -> None:
    # data ingestion
    logger.info("Starting ingestion...")
    ingest()

    # load embedding model
    logger.info("Building data index...")
    build_index()

    # intent classification
    logger.info("Running intent classifier...")
    intent = classify_intent(ClassifyIntentRequest(query=query)).intent
    # if general question recognized, then return
    if intent == Intent.GENERAL_QUESTION:
        logger.warning("General question detected, skipping RAG pipeline")
        return

    # RAG pipeline
    logger.info("Running retriever...")
    retrieved = retrieve(RetrieverRequest(query=query))

    logger.info("Generating response...")
    response = generate_response(GenerateResponseRequest(query=query, candidates=retrieved.candidates))

    logger.success(f"Response: {response}")

if __name__ == "__main__":
    run_pipeline("my honda fuel pump smells like shit")

