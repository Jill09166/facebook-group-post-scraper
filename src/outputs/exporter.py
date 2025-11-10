import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

import pandas as pd

def _ensure_output_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)

def _flatten_post(post: Dict[str, Any]) -> Dict[str, Any]:
    """
    Flatten nested post fields for CSV/XLSX output.
    """
    user = post.get("user") or {}
    flat = {
        "createdAt": post.get("createdAt"),
        "url": post.get("url"),
        "user.id": user.get("id"),
        "user.name": user.get("name"),
        "user.url": user.get("url"),
        "text": post.get("text"),
        "reactionCount": post.get("reactionCount", 0),
        "shareCount": post.get("shareCount", 0),
        "commentCount": post.get("commentCount", 0),
        # Serialize nested structures to JSON strings
        "attachments": json.dumps(post.get("attachments") or [], ensure_ascii=False),
        "topComments": json.dumps(post.get("topComments") or [], ensure_ascii=False),
    }
    return flat

def export_posts(
    posts: Sequence[Dict[str, Any]],
    output_dir: Path,
    base_filename: str,
    formats: Iterable[str],
    logger: logging.Logger | None = None,
) -> None:
    """
    Export scraped posts into selected formats (JSON, CSV, XLSX).

    :param posts: Sequence of post dictionaries.
    :param output_dir: Directory where output files will be written.
    :param base_filename: Base name for output files (without extension).
    :param formats: Iterable of formats to export: json, csv, xlsx.
    :param logger: Optional logger for progress reporting.
    """
    log = logger or logging.getLogger(__name__)
    if not posts:
        log.warning("No posts provided to exporter; skipping export.")
        return

    _ensure_output_dir(output_dir)
    formats = {fmt.lower() for fmt in formats}

    if "json" in formats:
        json_path = output_dir / f"{base_filename}.json"
        with json_path.open("w", encoding="utf-8") as f:
            json.dump(posts, f, ensure_ascii=False, indent=2)
        log.info("Exported %d posts to %s", len(posts), json_path)

    # Prepare flattened view for tabular exports
    flat_posts: List[Dict[str, Any]] = [_flatten_post(p) for p in posts]
    df = pd.DataFrame(flat_posts)

    if "csv" in formats:
        csv_path = output_dir / f"{base_filename}.csv"
        df.to_csv(csv_path, index=False)
        log.info("Exported %d posts to %s", len(posts), csv_path)

    if "xlsx" in formats:
        xlsx_path = output_dir / f"{base_filename}.xlsx"
        df.to_excel(xlsx_path, index=False)
        log.info("Exported %d posts to %s", len(posts), xlsx_path)