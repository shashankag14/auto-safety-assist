from fastapi import HTTPException, status
from loguru import logger

from src.ingestion.build_index import build_index
from src.ingestion.ingestion import ingest
from src.services.intent_classifier.classifier import classify_intent
from src.services.intent_classifier.schemas import ClassifyIntentRequest, Intent
from src.services.response_generator.generator import answer, generate_response
from src.services.response_generator.schemas import AnswerRequest, GenerateResponseRequest
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

    # general questions are answered without retrieval
    if intent == Intent.GENERAL_QUESTION:
        logger.info("General question detected, answering without retrieval...")
        response = answer(AnswerRequest(query=query))
        logger.success(f"Response: {response}")
        return

    # if the intent couldn't be parsed, run RAG anyway: a wasted retrieval is cheaper than
    # answering a recall/complaint question without data
    if intent is None:
        logger.warning("Intent could not be classified, running RAG pipeline anyway")

    # RAG pipeline
    logger.info("Running retriever...")
    try:
        retrieved = retrieve(RetrieverRequest(query=query))
    except HTTPException as e:
        if e.status_code != status.HTTP_404_NOT_FOUND:
            raise
        logger.warning("No matching recalls/complaints found, answering without retrieval...")
        response = answer(AnswerRequest(query=query))
        logger.success(f"Response: {response}")
        return

    logger.info("Generating response...")
    response = generate_response(GenerateResponseRequest(query=query, candidates=retrieved.candidates))

    logger.success(f"Response: {response}")

if __name__ == "__main__":
    run_pipeline("my honda fuel pump smells like shit")

