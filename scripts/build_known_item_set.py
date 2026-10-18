#!/usr/bin/env python3
"""Une los artículos de origen con sus descripciones y valida el conjunto de ítem conocido.

Cada descripción está redactada a mano como la escribiría un estudiante que busca
antecedentes. La validación rechaza dos formas de copia que harían trivial la
búsqueda: compartir una frase literal con el artículo y reutilizar sus términos
distintivos. No limita el vocabulario temático compartido, porque un estudiante que
busque literatura sobre psoriasis escribirá esa palabra; medirlo penalizaría más a
las consultas en inglés sobre artículos en inglés que a las consultas entre idiomas.
"""

import argparse
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

import pandas as pd
from langdetect import DetectorFactory, detect

from sisreco.settings import CATALOG, EVALUATION_DIR, SEED

DetectorFactory.seed = 42
MIN_SENTENCES, MAX_SENTENCES = 2, 4
# Una frase literal de cinco palabras compartida con el artículo es copia, no coincidencia.
PHRASE_LENGTH = 5
# Término distintivo: aparece en menos del 0,1 % de los artículos de su idioma. Se
# admiten hasta cuatro, porque nombrar el objeto de estudio es inevitable.
DISTINCTIVE_SHARE = 0.001
MAX_DISTINCTIVE_SHARED = 4
FREQUENCY_SAMPLE = 5_000
STOPWORDS = {
    "para", "con", "que", "los", "las", "del", "una", "uno", "por", "sobre", "como", "este", "esta",
    "quiero", "busco", "pienso", "mi", "proyecto", "grado", "tesis", "antecedentes", "estudio",
    "estudiar", "analizar", "investigacion", "trabajo", "me", "interesa", "interesan", "su", "sus",
    "the", "and", "for", "with", "that", "this", "want", "plan", "looking", "background", "project",
    "thesis", "degree", "study", "interested", "their", "its", "how", "whether", "from", "about",
    "also", "into", "have", "has", "which", "where", "them", "they", "not", "are", "can", "will",
}


def content_words(text: str) -> set[str]:
    folded = unicodedata.normalize("NFKD", text.casefold())
    folded = "".join(char for char in folded if not unicodedata.combining(char))
    return {word for word in re.findall(r"[a-z]{4,}", folded) if word not in STOPWORDS}


def sentence_count(text: str) -> int:
    return len([part for part in re.split(r"(?<=[.!?])\s+", text.strip()) if part])


def phrases(text: str, length: int = PHRASE_LENGTH) -> set[tuple[str, ...]]:
    words = re.findall(r"\w+", text.casefold())
    return {tuple(words[index:index + length]) for index in range(len(words) - length + 1)}


def distinctive_vocabulary(catalog: pd.DataFrame) -> dict[str, set[str]]:
    """Palabras poco frecuentes en cada idioma, estimadas sobre una muestra del catálogo."""
    vocabulary = {}
    for language, group in catalog.groupby("language"):
        sample = group.sample(min(FREQUENCY_SAMPLE, len(group)), random_state=SEED)
        counts = Counter()
        for title, abstract in zip(sample["title"], sample["abstract"]):
            counts.update(content_words(f"{title} {abstract}"))
        threshold = DISTINCTIVE_SHARE * len(sample)
        vocabulary[language] = {word for word, count in counts.items() if count < threshold}
    return vocabulary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--descriptions", nargs="+", type=Path,
                        default=[EVALUATION_DIR / "known_item_descriptions.jsonl"],
                        help="Archivos JSONL con query_id y description.")
    args = parser.parse_args()

    sources = pd.read_csv(EVALUATION_DIR / "known_item_sources.csv")
    catalog = pd.read_parquet(CATALOG).set_index("id")
    rows = []
    for path in args.descriptions:
        rows.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    descriptions = pd.DataFrame(rows)
    if descriptions["query_id"].duplicated().any():
        raise SystemExit("Hay query_id repetidos en las descripciones.")

    merged = sources.merge(descriptions, on="query_id", how="left", validate="one_to_one")
    if merged["description"].isna().any():
        missing = merged.loc[merged["description"].isna(), "query_id"].tolist()
        raise SystemExit(f"Faltan descripciones para: {missing}")

    distinctive = distinctive_vocabulary(pd.read_parquet(CATALOG))
    problems = []
    for index, row in merged.iterrows():
        article = catalog.loc[row["article_id"]]
        article_text = f"{article['title']} {article['abstract']}"
        detected = detect(row["description"])
        sentences = sentence_count(row["description"])
        shared_phrases = phrases(row["description"]) & phrases(article_text)
        shared_distinctive = (
            content_words(row["description"]) & content_words(article_text)
            & distinctive[row["query_language"]]
        )
        if detected != row["query_language"]:
            problems.append(f"{row['query_id']}: idioma {detected} en lugar de {row['query_language']}")
        if not MIN_SENTENCES <= sentences <= MAX_SENTENCES:
            problems.append(f"{row['query_id']}: {sentences} oraciones")
        if shared_phrases:
            problems.append(f"{row['query_id']}: frase copiada «{' '.join(next(iter(shared_phrases)))}»")
        if len(shared_distinctive) > MAX_DISTINCTIVE_SHARED:
            problems.append(f"{row['query_id']}: {len(shared_distinctive)} términos distintivos reutilizados: {sorted(shared_distinctive)}")
        merged.loc[index, "shared_distinctive_terms"] = len(shared_distinctive)
    if problems:
        raise SystemExit("Revisa las descripciones:\n" + "\n".join(problems))

    output = EVALUATION_DIR / "known_item.jsonl"
    columns = ["query_id", "description", "query_language", "article_id", "article_language",
               "source_database", "field", "topic", "shared_distinctive_terms"]
    merged["shared_distinctive_terms"] = merged["shared_distinctive_terms"].astype(int)
    with output.open("w", encoding="utf-8") as target:
        for _, row in merged[columns].iterrows():
            target.write(json.dumps(row.to_dict(), ensure_ascii=False) + "\n")
    print(f"{len(merged)} consultas en {output}")
    print(merged.groupby(["source_database", "article_language", "query_language"]).size().to_string())
    print(f"Consultas sin ninguna frase copiada: {len(merged)}")
    print(f"Términos distintivos reutilizados: media {merged['shared_distinctive_terms'].mean():.2f}, "
          f"máximo {merged['shared_distinctive_terms'].max()}, "
          f"ninguno en {(merged['shared_distinctive_terms'] == 0).sum()} consultas")


if __name__ == "__main__":
    main()
