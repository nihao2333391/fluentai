"""Read-only local retrieval over the reviewed boundary-layer rule files."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import Any

KNOWLEDGE_DIR = Path(__file__).with_name("knowledge")
SOURCE_FILES = (
    "原有_层数推荐算法说明.md",
    "Uniform_First_Height_计算封装说明.md",
)
MAX_QUERY_LENGTH = 400
MAX_RESULTS = 4
MAX_EXCERPT_LENGTH = 1_600


def _compact(text: str) -> str:
    return "".join(
        character.lower()
        for character in text
        if character.isalnum() or "\u3400" <= character <= "\u9fff"
    )


def _terms(text: str) -> set[str]:
    terms = set(re.findall(r"[a-z][a-z0-9_+-]*|\d+(?:\.\d+)?", text.lower()))
    for run in re.findall(r"[\u3400-\u9fff]+", text):
        for size in (2, 3):
            terms.update(run[index : index + size] for index in range(len(run) - size + 1))
    return terms


def _split_sections(source: str, content: str) -> list[dict[str, str]]:
    parts = re.split(r"(?=^#{1,6}\s+)", content, flags=re.MULTILINE)
    sections: list[dict[str, str]] = []
    for index, part in enumerate(parts):
        lines = part.strip().splitlines()
        if not lines:
            continue
        is_heading = lines[0].startswith("#")
        heading = re.sub(r"^#{1,6}\s+", "", lines[0]).strip() if is_heading else ""
        body = "\n".join(lines[1:] if is_heading else lines).strip()
        if body:
            sections.append(
                {"source": source, "section": heading or f"引言 {index + 1}", "content": body}
            )
    return sections


@lru_cache(maxsize=1)
def _load_sections() -> tuple[dict[str, Any], ...]:
    sections: list[dict[str, Any]] = []
    for filename in SOURCE_FILES:
        path = KNOWLEDGE_DIR / filename
        if path.is_file():
            sections.extend(_split_sections(filename, path.read_text(encoding="utf-8")))
    return tuple(sections)


def search_boundary_layer_rules(
    query: str, allowed_sources: tuple[str, ...] | None = None
) -> dict[str, Any]:
    """Search local boundary-layer rules and return passages with source citations.

    Use before answering questions about the project's Uniform or Smooth Transition
    rules. Results include the original source filename and Markdown heading.
    """
    question = str(query).strip()
    if not question:
        raise ValueError("请提供要检索的边界层问题。")
    if len(question) > MAX_QUERY_LENGTH:
        raise ValueError(f"检索问题不能超过 {MAX_QUERY_LENGTH} 个字符。")

    query_terms = _terms(question)
    compact_query = _compact(question)
    ranked: list[tuple[float, dict[str, Any]]] = []
    for section in _load_sections():
        if allowed_sources is not None and section["source"] not in allowed_sources:
            continue
        body = str(section["content"])
        searchable = f"{section['section']}\n{body}"
        matched = query_terms & _terms(searchable)
        if not matched:
            continue
        coverage = len(matched) / max(1, len(query_terms))
        score = sum(1.0 + 0.15 * min(len(term), 5) for term in matched)
        score = score * (0.5 + coverage) / math.sqrt(1 + len(body) / 1_800)
        if len(compact_query) >= 5 and compact_query in _compact(searchable):
            score += 8.0
        ranked.append((score, section))

    ranked.sort(key=lambda item: (-item[0], item[1]["source"], item[1]["section"]))
    results = [
        {
            "source": section["source"],
            "section": section["section"],
            "excerpt": str(section["content"])[:MAX_EXCERPT_LENGTH],
        }
        for _, section in ranked[:MAX_RESULTS]
    ]
    return {
        "status": "matched" if results else "no_match",
        "query": question,
        "results": results,
        "message": "回答时标注命中的来源文件和章节；无命中时说明本地规则中未找到依据。",
    }


_search_impl = search_boundary_layer_rules


def create_scoped_boundary_layer_search(
    allowed_sources: tuple[str, ...],
) -> Callable[[str], str]:
    """Create an Agno-callable search tool limited to an explicit source allowlist."""

    def search_boundary_layer_rules(query: str) -> str:
        """Search only the engineering knowledge files authorized for this template."""
        # Agno stringifies non-string results via str(), which would turn the dict
        # into a Python repr that downstream json.loads consumers cannot parse.
        return json.dumps(_search_impl(query, allowed_sources=allowed_sources), ensure_ascii=False)

    search_boundary_layer_rules.__name__ = "search_boundary_layer_rules"
    search_boundary_layer_rules.__qualname__ = "search_boundary_layer_rules"
    search_boundary_layer_rules.__doc__ = (
        "Search only the locally configured engineering rule files for this template. "
        "Return exact source filenames, headings, and passages."
    )
    return search_boundary_layer_rules
