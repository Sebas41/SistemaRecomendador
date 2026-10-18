#!/usr/bin/env python3
"""Prepara la hoja ciega de verificación humana con los perfiles de data/evaluation/topics.jsonl.

Para cada perfil y cada idioma de la consulta se toma el top 5 de la configuración de
referencia y el de la configuración elegida, sin filtros. Cada artículo aparece una sola
vez por perfil, en orden aleatorio y sin indicar de qué configuración viene; la llave
queda en un archivo aparte que se consulta después de calificar.
"""

import argparse
import json

import pandas as pd

from evaluate_configs import CONFIGS, ensure_vectors
from sisreco.engine import load_retriever, recommend
from sisreco.settings import ARTIFACTS_DIR, CATALOG, EVALUATION_DIR, SEED

TOP_RATED = 5


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", default="A", choices=sorted(CONFIGS))
    parser.add_argument("--chosen", required=True, choices=sorted(CONFIGS))
    args = parser.parse_args()

    catalog = pd.read_parquet(CATALOG)
    profiles = [json.loads(line) for line in (EVALUATION_DIR / "topics.jsonl").read_text(encoding="utf-8").splitlines()]
    rankings = []
    for config in (args.reference, args.chosen):
        retriever_spec, reranker_spec = CONFIGS[config]
        vectors = ensure_vectors(catalog, retriever_spec)
        retriever = load_retriever(retriever_spec)
        for profile in profiles:
            for language in ("es", "en"):
                results = recommend(catalog, profile[language], top_k=TOP_RATED, vectors=vectors, retriever=retriever,
                                    retriever_spec=retriever_spec, reranker_spec=reranker_spec, generate_evidence=False)
                rankings.extend({"profile_id": profile["profile_id"], "query_language": language, "config": config,
                                 "rank": rank, "article_id": article_id}
                                for rank, article_id in enumerate(results["id"], start=1))
    rankings = pd.DataFrame(rankings)

    articles = catalog.set_index("id")
    topics = {profile["profile_id"]: profile for profile in profiles}
    sheet = rankings.drop_duplicates(["profile_id", "article_id"])[["profile_id", "article_id"]]
    # Orden aleatorio dentro de cada perfil para que la posición no delate la configuración.
    sheet = sheet.sample(frac=1, random_state=SEED).sort_values("profile_id", kind="stable").reset_index(drop=True)
    sheet["profile_description_es"] = sheet["profile_id"].map(lambda pid: topics[pid]["es"])
    for column in ("title", "abstract", "year", "language", "source_database", "url"):
        sheet[column] = sheet["article_id"].map(articles[column])
    sheet["relevance"] = ""

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    sheet.to_csv(ARTIFACTS_DIR / "human_ratings.csv", index=False)
    rankings.to_csv(ARTIFACTS_DIR / "human_ratings_key.csv", index=False)
    print(f"Artículos a calificar: {len(sheet)} en {sheet['profile_id'].nunique()} perfiles "
          f"({len(rankings)} posiciones ordenadas en total).")
    print(f"Completa relevance en {ARTIFACTS_DIR / 'human_ratings.csv'} siguiendo docs/guia_calificacion.md.")


if __name__ == "__main__":
    main()
