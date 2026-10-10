"""Configuración central y rutas reproducibles del proyecto."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
ARTIFACTS_DIR = ROOT / "artifacts"
RAW_CATALOG = RAW_DIR / "openalex_works.jsonl.gz"
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
START_YEAR = 2016
END_YEAR = 2025
TARGET_PER_FIELD = 300
MINIMUM_PER_FIELD = 100
MAX_ABSTRACT_WORDS = 1200
MIN_ABSTRACT_WORDS = 80
MAX_TITLE_WORDS = 100
SEED = 42
FIELD_SAMPLE_SIZE = 1000
MAX_SAMPLE_ATTEMPTS = 10
PAGE_SIZE = 100
EMBEDDING_BATCH_SIZE = 48
TOP_K_OPTIONS = (5, 10)
