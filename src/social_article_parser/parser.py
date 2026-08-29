from __future__ import annotations

import math
import re
from difflib import SequenceMatcher

from .adapters import DEFAULT_ADAPTERS, SourceAdapter
from .dom import Node, is_noise, markdown_from_node, parse_html, select, serialize, text_lengths, visible_text
from .metadata import extract_metadata
from .models import ArticleMetadata, Candidate
from .selectors import CONTENT_TAGS, WECHAT_CONTENT_SELECTORS


class ArticleParser:
    """Orchestrates independent extraction strategies and chooses a scored result."""

    def __init__(self, adapters: tuple[SourceAdapter, ...] | None = None) -> None:
        self.adapters = DEFAULT_ADAPTERS if adapters is None else adapters

    def parse(self, html: str) -> tuple[str, ArticleMetadata, str]:
        root = parse_html(html)
        metadata_values = extract_metadata(root)
        candidates = []
        for adapter in self.adapters:
            candidates.extend(adapter.candidates(root))
        # Platform-specific containers are much more reliable than generic page
        # scoring and avoid re-scanning thousands of wrappers in saved WeChat HTML.
        if not candidates:
            candidates.extend(self._generic_candidates(root))
        candidates = self._score_and_dedupe(candidates, metadata_values.get("title", ""))

        if not candidates:
            metadata = ArticleMetadata(
                **metadata_values,
                extractor="none",
                original_html_length=len(html),
                status="low_confidence",
                reasons=["页面中没有找到可渲染的正文候选。"],
            )
            return self._render_document("", metadata), metadata, ""

        best = candidates[0]
        markdown, image_count = markdown_from_node(best.root)  # type: ignore[arg-type]
        body_text = visible_text(best.root)  # type: ignore[arg-type]
        confidence, reasons = self._confidence(best, markdown)
        metadata = ArticleMetadata(
            **metadata_values,
            extractor=best.name,
            confidence=confidence,
            original_html_length=len(html),
            clean_text_length=len(body_text),
            image_count=image_count,
            status="ok" if confidence >= 0.60 else "low_confidence",
            reasons=reasons,
        )
        # The candidate HTML is only used for low-confidence CLI diagnostics.
        # Avoid rebuilding a large subtree on ordinary successful parses.
        candidate_html = serialize(best.root) if metadata.status == "low_confidence" else ""  # type: ignore[arg-type]
        return self._render_document(markdown, metadata), metadata, candidate_html

    def _generic_candidates(self, root: Node) -> list[Candidate]:
        candidates: list[tuple[int, Candidate]] = []
        lengths = text_lengths(root)
        for node in root.walk():
            if node.tag not in CONTENT_TAGS or is_noise(node):
                continue
            length = lengths[id(node)]
            if length < 120:
                continue
            # Body/html-like wrappers are intentionally considered only as poor fallbacks.
            depth = self._depth(node)
            if node.tag in {"body", "html"}:
                continue
            candidates.append((length, Candidate(f"generic:{node.tag}@depth{depth}", node)))
        # Large saved pages can contain thousands of nested wrappers. Keeping the
        # strongest few dozen candidates prevents repeated subtree traversal from
        # turning parsing into an O(n²) operation.
        candidates.sort(key=lambda item: item[0], reverse=True)
        return [candidate for _, candidate in candidates[:12]]

    def _score_and_dedupe(self, candidates: list[Candidate], title: str) -> list[Candidate]:
        scored: list[Candidate] = []
        text_cache: dict[int, str] = {}
        # A malformed page may repeat article-like wrappers thousands of times.
        # The exact platform containers are encountered first; examining more than
        # a small set brings no extraction benefit and can turn into repeated
        # subtree work.
        for candidate in candidates[:24]:
            text = visible_text(candidate.root)  # type: ignore[arg-type]
            text_cache[id(candidate)] = text
            if len(text) < 40:
                continue
            candidate.text_length = len(text)
            candidate.chinese_ratio = self._chinese_ratio(text)
            candidate.paragraph_count = sum(1 for block in text.split("\n\n") if len(re.sub(r"\W", "", block)) >= 15)
            candidate.link_ratio = self._link_ratio(candidate.root)  # type: ignore[arg-type]
            candidate.noise_hits = self._noise_hits(candidate.root)  # type: ignore[arg-type]
            candidate.score = self._score(candidate, title, text)
            scored.append(candidate)

        scored.sort(key=lambda item: item.score, reverse=True)
        unique: list[Candidate] = []
        for candidate in scored:
            candidate_text = text_cache[id(candidate)]
            if any(self._near_duplicate(candidate_text, text_cache[id(other)]) for other in unique):
                continue
            unique.append(candidate)
            if len(unique) >= 30:
                break
        return unique

    def _score(self, candidate: Candidate, title: str, text: str) -> float:
        length_score = min(38.0, math.log1p(candidate.text_length) * 5.0)
        language_score = candidate.chinese_ratio * 18.0
        paragraphs_score = min(18.0, candidate.paragraph_count * 2.5)
        known_bonus = 15.0 if candidate.name.startswith("wechat_dom") else 10.0 if candidate.name.endswith("embedded_article_data") else 0.0
        title_bonus = 4.0 if title and self._title_related(title, text) else 0.0
        link_penalty = min(20.0, candidate.link_ratio * 25.0)
        noise_penalty = min(18.0, candidate.noise_hits * 3.0)
        wrapper_penalty = 11.0 if self._depth(candidate.root) < 3 and candidate.name.startswith("generic") else 0.0  # type: ignore[arg-type]
        return max(0.0, min(100.0, length_score + language_score + paragraphs_score + known_bonus + title_bonus - link_penalty - noise_penalty - wrapper_penalty))

    @staticmethod
    def _chinese_ratio(text: str) -> float:
        meaningful = [char for char in text if char.isalpha() or "\u4e00" <= char <= "\u9fff"]
        if not meaningful:
            return 0.0
        return sum("\u4e00" <= char <= "\u9fff" for char in meaningful) / len(meaningful)

    @staticmethod
    def _title_related(title: str, text: str) -> bool:
        key = re.sub(r"\W", "", title)[:12]
        return bool(key and key in re.sub(r"\W", "", text))

    @staticmethod
    def _depth(node: Node) -> int:
        depth = 0
        while node.parent:
            depth += 1
            node = node.parent
        return depth

    @staticmethod
    def _link_ratio(node: Node) -> float:
        text = visible_text(node)
        if not text:
            return 1.0
        linked = sum(len(visible_text(link)) for link in select(node, "a"))
        return min(1.0, linked / max(len(text), 1))

    @staticmethod
    def _noise_hits(node: Node) -> int:
        return sum(1 for item in node.walk() if item is not node and is_noise(item))

    @staticmethod
    def _near_duplicate(left: str, right: str) -> bool:
        left = re.sub(r"\s+", "", left)
        right = re.sub(r"\s+", "", right)
        if not left or not right:
            return False
        short, long = sorted((left, right), key=len)
        if len(short) / len(long) > 0.93:
            return SequenceMatcher(None, short[:5000], long[:5000]).ratio() > 0.90
        return short in long and len(short) > 300

    @staticmethod
    def _confidence(candidate: Candidate, markdown: str) -> tuple[float, list[str]]:
        reasons: list[str] = []
        score_confidence = candidate.score / 100.0
        if candidate.text_length < 180:
            reasons.append("候选正文较短，无法确认是否完整。")
            score_confidence -= 0.18
        if candidate.paragraph_count < 2:
            reasons.append("连续自然语言段落不足，可能是页面框架或截断内容。")
            score_confidence -= 0.15
        if candidate.link_ratio > 0.35:
            reasons.append("链接文字占比较高，可能混入导航或推荐内容。")
            score_confidence -= 0.12
        if not candidate.name.startswith(("wechat_dom", "wechat_embedded_article_data")):
            reasons.append("未命中特定来源结构，使用通用正文识别。")
            score_confidence -= 0.08
        if not markdown:
            reasons.append("清洗后没有保留可读正文。")
            score_confidence = 0.0
        return round(max(0.0, min(1.0, score_confidence)), 2), reasons

    @staticmethod
    def _render_document(body: str, metadata: ArticleMetadata) -> str:
        header: list[str] = []
        if metadata.title:
            header.append(f"# {metadata.title}")
        details = []
        if metadata.author:
            details.append(f"作者：{metadata.author}")
        if metadata.account:
            details.append(f"公众号：{metadata.account}")
        if metadata.publish_time:
            details.append(f"发布时间：{metadata.publish_time}")
        if metadata.url:
            details.append(f"原文：{metadata.url}")
        if details:
            header.append("\n".join(details))
        if header and body:
            return "\n\n".join(header) + "\n\n---\n\n" + body + "\n"
        return ("\n\n".join(header + [body])).strip() + "\n"
