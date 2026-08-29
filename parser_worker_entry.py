from __future__ import annotations

import argparse
from pathlib import Path

from social_article_parser import ArticleParser


def main() -> int:
    parser = argparse.ArgumentParser(description="Social article parser worker")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    html = args.input.read_text(encoding="utf-8")
    document, _metadata, _candidate_html = ArticleParser().parse(html)
    args.output.write_text(document, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
