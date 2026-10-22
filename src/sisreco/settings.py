"""Configuración central y rutas reproducibles del proyecto."""

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
ARTIFACTS_DIR = ROOT / "artifacts"
EVALUATION_DIR = ROOT / "data" / "evaluation"
RAW_CATALOG = RAW_DIR / "openalex_works.jsonl.gz"
RAW_SCIELO_CATALOG = RAW_DIR / "scielo_articles.jsonl.gz"
RAW_SCIELO_SAMPLE_MANIFEST = RAW_DIR / "scielo_sample_manifest.json"
RAW_OPENALEX_SAMPLE_MANIFEST = RAW_DIR / "openalex_sample_manifest.json"
CATALOG = PROCESSED_DIR / "catalog.parquet"
DATA_MANIFEST = PROCESSED_DIR / "dataset_manifest.json"
TFIDF_VECTORIZER = ARTIFACTS_DIR / "tfidf_vectorizer.joblib"
TFIDF_MATRIX = ARTIFACTS_DIR / "tfidf_matrix.npz"
TFIDF_IDS = ARTIFACTS_DIR / "tfidf_ids.json"
HYBRID_VECTORIZER = ARTIFACTS_DIR / "hybrid_tfidf_vectorizer.joblib"
HYBRID_MATRIX = ARTIFACTS_DIR / "hybrid_tfidf_matrix.npz"
HYBRID_MANIFEST = ARTIFACTS_DIR / "hybrid_tfidf_manifest.json"
HYBRID_MAX_FEATURES = 60_000
HYBRID_RRF_K = 60
OPENALEX_BASE_URL = "https://api.openalex.org"
SCIELO_API_BASE_URL = "https://articlemeta.scielo.org/api/v1"
SCIELO_COLLECTIONS = (
    "arg", "bol", "chl", "col", "cri", "cub", "dom", "ecu", "esp",
    "mex", "per", "prt", "pry", "scl", "spa", "sss", "sza", "ury", "ven",
)
START_YEAR = 2016
END_YEAR = 2025
TARGET_PER_FIELD = 4800
MINIMUM_PER_FIELD = 100
MAX_ABSTRACT_WORDS = 1200
MIN_ABSTRACT_WORDS = 80
MAX_TITLE_WORDS = 100
SEED = 42
FIELD_SAMPLE_SIZE = 6000
MAX_SAMPLE_ATTEMPTS = 3
PAGE_SIZE = 100
SCIELO_PAGE_SIZE = 100
SCIELO_PAGES_PER_COLLECTION = 3
SCIELO_REQUEST_INTERVAL_SECONDS = 0.4
MINIMUM_CATALOG_SIZE = 100_000
EMBEDDING_BATCH_SIZE = 16
TOP_K = 10


@dataclass(frozen=True)
class RetrieverSpec:
    """Modelo que convierte consultas y artículos en vectores comparables por coseno."""

    model_name: str
    max_seq_length: int
    vectors_path: Path
    query_prefix: str = ""
    document_prefix: str = ""


@dataclass(frozen=True)
class RerankerSpec:
    """Modelo que lee la consulta y cada candidato juntos para reordenar la lista corta."""

    model_name: str
    max_length: int
    candidates: int


# bge-m3 procesa hasta 8.192 tokens; 1.024 cubre completo el 99,3 % del texto indexado
# (percentil 99 = 938 tokens) con una fracción del costo de memoria de la ventana completa.
RETRIEVER = RetrieverSpec("BAAI/bge-m3", max_seq_length=1024, vectors_path=ARTIFACTS_DIR / "bge_m3.npy")
RERANKER = RerankerSpec("BAAI/bge-reranker-v2-m3", max_length=512, candidates=100)
