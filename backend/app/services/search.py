"""BM25 search service for paper paragraphs."""

import numpy as np
from rank_bm25 import BM25Okapi
from typing import List, Dict, Any
from pathlib import Path
import frontmatter
import re


class BM25Search:
    def __init__(self, paper_id: str, data_dir: Path):
        self.paper_id = paper_id
        self.data_dir = Path(data_dir)
        self.paragraphs = []
        self.bm25 = None
        self.title = "Unknown Paper"
        self._load_and_index()

    def _load_and_index(self):
        content_path = self.data_dir / "papers" / self.paper_id / "content.md"

        if not content_path.exists():
            return

        with open(content_path, "r", encoding="utf-8") as f:
            post = frontmatter.load(f)
            self.title = post.metadata.get("title", "Unknown Paper")

            if "paragraphs" in post.metadata:
                self.paragraphs = [
                    {"id": p["id"], "text": p["text"]}
                    for p in post.metadata["paragraphs"]
                ]
            else:
                self.paragraphs = self._extract_paragraphs(post.content)

        if self.paragraphs:
            tokenized = [p["text"].split() for p in self.paragraphs]
            self.bm25 = BM25Okapi(tokenized)

    def _extract_paragraphs(self, content: str) -> List[Dict[str, str]]:
        paras = re.split(r"\n\n+", content)
        return [
            {"id": f"para_{i}", "text": p.strip()[:1000]}
            for i, p in enumerate(paras)
            if len(p.strip()) > 50
        ]

    def search(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        if not self.paragraphs or not self.bm25:
            return []

        tokenized_query = query.split()
        if not tokenized_query:
            return []

        scores = self.bm25.get_scores(tokenized_query)
        top_indices = np.argsort(scores)[-top_k:][::-1]

        return [
            {
                "id": self.paragraphs[i]["id"],
                "text": self.paragraphs[i]["text"],
                "score": float(scores[i]),
            }
            for i in top_indices
            if len(self.paragraphs) > i
        ]
