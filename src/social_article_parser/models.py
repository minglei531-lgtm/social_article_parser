from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(slots=True)
class ArticleMetadata:
    title: str = ""
    author: str = ""
    account: str = ""
    publish_time: str = ""
    url: str = ""
    extractor: str = ""
    confidence: float = 0.0
    original_html_length: int = 0
    clean_text_length: int = 0
    image_count: int = 0
    status: str = "low_confidence"
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class Candidate:
    name: str
    root: object
    score: float = 0.0
    text_length: int = 0
    chinese_ratio: float = 0.0
    paragraph_count: int = 0
    link_ratio: float = 0.0
    noise_hits: int = 0
    html: str = ""
