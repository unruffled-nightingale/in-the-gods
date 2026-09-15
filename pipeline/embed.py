#!/usr/bin/env python3
"""Bake MiniLM vectors for the current extract.

    python pipeline/embed.py
    python pipeline/embed.py --in data/extracts/latest.json --out data/extracts/latest.embeddings.npz
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.vectors import EMBEDDINGS, EXTRACT, MODEL, embed_extract  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in", dest="src", default=str(EXTRACT))
    ap.add_argument("--out", dest="dest", default=str(EMBEDDINGS))
    args = ap.parse_args()
    dest = embed_extract(Path(args.src), Path(args.dest))
    data = __import__("numpy").load(dest)
    rows, dim = data["vectors"].shape
    shows = len(set(data["owners"].tolist())) if "owners" in data.files else rows
    print(f"embed: {rows} chunks / {shows} shows x {dim} ({MODEL}) -> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
