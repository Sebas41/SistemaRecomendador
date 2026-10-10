#!/usr/bin/env python3
"""Añade revisión y tasa de truncado del modelo al manifiesto local."""

import json
import numpy as np
import pandas as pd

from sisreco.engine import _load_sentence_model, _model_provenance
from sisreco.settings import CATALOG, EMBEDDINGS, EMBEDDINGS_MANIFEST


def main():
    if not CATALOG.exists() or not EMBEDDINGS.exists() or not EMBEDDINGS_MANIFEST.exists():
        raise SystemExit("Prepara el catálogo y los vectores con sus scripts de descarga e indexación.")
    catalog = pd.read_parquet(CATALOG)
    if np.load(EMBEDDINGS, mmap_mode="r").shape[0] != len(catalog):
        raise SystemExit("El índice vectorial no corresponde al catálogo actual.")
    model = _load_sentence_model()
    provenance = _model_provenance(model, catalog)
    manifest = json.loads(EMBEDDINGS_MANIFEST.read_text(encoding="utf-8"))
    manifest["revision"] = provenance["model_revision"]
    manifest["truncated_documents"] = provenance["truncated_documents"]
    manifest["truncated_fraction"] = provenance["truncated_documents"] / len(catalog)
    EMBEDDINGS_MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Revisión del modelo: {manifest['revision']}")
    print(f"Documentos sobre el límite de 512 tokens: {manifest['truncated_documents']}/{len(catalog)}")


if __name__ == "__main__":
    main()
