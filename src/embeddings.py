"""
src/embeddings.py — PolígrafoES
Embeddings multilingües para cruzar votaciones con programas electorales.

multilingual-e5-small exige prefijos: "query: " para el texto de búsqueda y
"passage: " para los documentos indexados. Sin ellos la calidad cae.
"""
import numpy as np

MODEL_NAME = "intfloat/multilingual-e5-small"
DIM = 384

_model = None


def _get_model():
    """Carga perezosa: importar sentence-transformers cuesta segundos."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def embed_texts(textos, prefijo):
    """
    textos: list[str]. prefijo: "query: " o "passage: ".
    Returns: np.ndarray (n, DIM) float32, filas normalizadas → el producto
    escalar entre dos filas es directamente su similitud coseno.
    """
    if not textos:
        return np.zeros((0, DIM), dtype=np.float32)
    vectores = _get_model().encode(
        [prefijo + t for t in textos],
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return np.asarray(vectores, dtype=np.float32)


def to_blob(vector):
    return np.asarray(vector, dtype=np.float32).tobytes()


def from_blob(blob):
    return np.frombuffer(blob, dtype=np.float32)
