from loguru import logger
from sentence_transformers import SentenceTransformer


def get_embedding_model(model_name: str = "all-MiniLM-L6-v2") -> SentenceTransformer:
    """Load the embedding model from sentence-transformers."""
    emb_model = SentenceTransformer(model_name)
    logger.info("Embedding model loaded successfully!")
    return emb_model
