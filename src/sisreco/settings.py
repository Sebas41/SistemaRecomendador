"""Configuración central y rutas reproducibles del proyecto."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
ARTIFACTS_DIR = ROOT / "artifacts"
RAW_CATALOG = RAW_DIR / "openalex_works.jsonl.gz"
RAW_SCIELO_CATALOG = RAW_DIR / "scielo_articles.jsonl.gz"
RAW_SCIELO_SAMPLE_MANIFEST = RAW_DIR / "scielo_sample_manifest.json"
RAW_OPENALEX_SAMPLE_MANIFEST = RAW_DIR / "openalex_sample_manifest.json"
CATALOG = PROCESSED_DIR / "catalog.parquet"
DATA_MANIFEST = PROCESSED_DIR / "dataset_manifest.json"
EMBEDDINGS = ARTIFACTS_DIR / "multilingual_e5_small.npy"
EMBEDDINGS_MANIFEST = ARTIFACTS_DIR / "embeddings_manifest.json"
TFIDF_VECTORIZER = ARTIFACTS_DIR / "tfidf_vectorizer.joblib"
TFIDF_MATRIX = ARTIFACTS_DIR / "tfidf_matrix.npz"
TFIDF_IDS = ARTIFACTS_DIR / "tfidf_ids.json"
MODEL_NAME = "intfloat/multilingual-e5-small"
MODEL_REVISION = "main"
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
EMBEDDING_BATCH_SIZE = 48
TOP_K_OPTIONS = (5, 10)
