import logging
import threading

import numpy as np
from sentence_transformers import SentenceTransformer

from pib_agent.config import get_settings

logger = logging.getLogger(__name__)

_model: SentenceTransformer | None = None
_model_lock = threading.Lock()


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                settings = get_settings()
                logger.info("Loading sentence-transformers model %r", settings.embedding_model)
                _model = SentenceTransformer(settings.embedding_model)
    return _model


def embed_text(text: str) -> np.ndarray:
    """Embed a single string into a unit-normalized float32 vector.

    Normalized so cosine similarity between two embeddings is a plain dot product.
    """
    model = _get_model()
    vector = model.encode(text, normalize_embeddings=True)
    return np.asarray(vector, dtype=np.float32)
