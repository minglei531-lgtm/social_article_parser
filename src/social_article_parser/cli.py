from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from .parser import ArticleParser


def _safe_stem(value: str) -> str:
    value = re.sub(r'[<>:"/\\\\|?*\x00-\x1f]', "_", value).strip(" .")
    return value[:100] or "article"


def _to_txt(markdown: str) -> str:
    value = re.sub(r"^#{1,6} +", "", markdown, flags=re.M)
    value = re.sub(r"^> ?", "", value, flags=re.M)
    value = re.sub(r"^---$", "", value, flags=re.M)
    return re.sub(r"\n{3,}", "\n\n", value).strip() + "\n"


def _read_html(path: Path) -> str:
    last_error: UnicodeDecodeError | None = None
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError as error:
            last_error = error
    assert last_error is not None
    raise last_error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="本地社媒文章 HTML → 干净 Markdown/TXT")
    parser.add_argument("html", type=Path, help="浏览器保存的 HTML 文件")
    parser.add_argument("--output-dir", "-o", type=Path, default=Path("output"), help="输出目录（默认：output）")
    parser.add_argument("--format", choices=("md", "txt"), default="md", help="正文格式（默认：md）")
    args = parser.parse_args(argv)
    try:
        html = _read_html(args.html)
    except OSError as error:
        parser.error(f"无法读取 HTML：{error}")

    document, metadata, candidate_html = ArticleParser().parse(html)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stem = _safe_stem(metadata.title or args.html.stem)
    article_path = args.output_dir / f"{stem}.{args.format}"
    article_path.write_text(document if args.format == "md" else _to_txt(document), encoding="utf-8")
    metadata_path = args.output_dir / f"{stem}.metadata.json"
    metadata_path.write_text(json.dumps(metadata.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if metadata.status == "low_confidence" and candidate_html:
        (args.output_dir / f"{stem}.candidate.html").write_text(candidate_html, encoding="utf-8")

    print(f"状态：{metadata.status}；提取器：{metadata.extractor}；置信度：{metadata.confidence:.0%}")
    print(f"正文：{article_path}")
    print(f"元数据：{metadata_path}")
    return 0 if metadata.status == "ok" else 2
