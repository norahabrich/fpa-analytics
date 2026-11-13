"""Couche Bronze : archivage des réponses brutes et journal de collecte.

Chaque fichier est rangé par source, jeu de données, entreprise et date de collecte :

    data/bronze/sec/companyfacts/CIK0000027419/2026-11-13/companyfacts.json

Le journal `data/bronze/_ingestion_log.jsonl` garde une ligne par collecte (URL, date,
taille, empreinte SHA-256), ce qui rend chaque chiffre du projet traçable jusqu'à sa source.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

LOG_NAME = "_ingestion_log.jsonl"


@dataclass(frozen=True)
class IngestionRecord:
    retrieved_at: str
    source: str
    dataset: str
    cik: str
    url: str
    path: str
    bytes: int
    sha256: str
    status: str  # "new" ou "unchanged"


def bronze_path(
    root: Path, source: str, dataset: str, cik: str, retrieved_at: datetime, filename: str | None = None
) -> Path:
    name = filename or f"{dataset}.json"
    return root / source / dataset / f"CIK{cik}" / f"{retrieved_at:%Y-%m-%d}" / name


def archive(
    content: bytes,
    *,
    root: Path,
    source: str,
    dataset: str,
    cik: str,
    url: str,
    retrieved_at: datetime,
    filename: str | None = None,
) -> IngestionRecord:
    """Écrit le contenu brut (sans le modifier) et ajoute une ligne au journal.

    Une seconde collecte le même jour avec un contenu identique ne réécrit pas le
    fichier ; un contenu différent le remplace et le journal garde les deux empreintes.
    """
    target = bronze_path(root, source, dataset, cik, retrieved_at, filename)
    if target.suffix == ".json":
        json.loads(content)  # refuse d'archiver une réponse JSON invalide (page d'erreur, coupure)
    digest = hashlib.sha256(content).hexdigest()

    status = "new"
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == digest:
        status = "unchanged"
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".tmp")
        tmp.write_bytes(content)
        tmp.replace(target)

    record = IngestionRecord(
        retrieved_at=retrieved_at.isoformat(timespec="seconds"),
        source=source,
        dataset=dataset,
        cik=cik,
        url=url,
        path=target.relative_to(root).as_posix(),
        bytes=len(content),
        sha256=digest,
        status=status,
    )
    root.mkdir(parents=True, exist_ok=True)
    with (root / LOG_NAME).open("a", encoding="utf-8") as log:
        log.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
    return record


def latest_snapshot(root: Path, source: str, dataset: str, cik: str) -> Path:
    """Chemin du fichier archivé le plus récent pour ce jeu de données."""
    base = root / source / dataset / f"CIK{cik}"
    snapshots = sorted(p for p in base.glob(f"*/{dataset}.json"))
    if not snapshots:
        raise FileNotFoundError(f"Aucune archive sous {base}")
    return snapshots[-1]
