from __future__ import annotations

import datetime as dt
import re
from html import unescape

from .dom import Node, parse_html, visible_text


def _script_text(root: Node) -> str:
    return "\n".join(
        "".join(child for child in node.children if isinstance(child, str))
        for node in root.walk()
        if node.tag == "script"
    )


def decode_js_string(value: str) -> str:
    """Decode the limited string escapes used by WeChat page data, safely."""
    def replacement(match: re.Match[str]) -> str:
        raw = match.group(1)
        table = {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f", "v": "\v", "0": "\0"}
        if raw in table:
            return table[raw]
        if raw.startswith("x") and len(raw) == 3:
            try:
                return chr(int(raw[1:], 16))
            except ValueError:
                return match.group(0)
        if raw.startswith("u") and len(raw) == 5:
            try:
                return chr(int(raw[1:], 16))
            except ValueError:
                return match.group(0)
        return raw

    # Some archived pages have been string-escaped twice by an intermediate saver.
    # A bounded second pass restores those without attempting to execute JavaScript.
    for _ in range(2):
        decoded = re.sub(r"\\(u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}|[nrtbfv0\\\"'])", replacement, value)
        if decoded == value:
            break
        value = decoded
    return unescape(value)


def find_script_string(script: str, key: str) -> str:
    """Read a quoted JavaScript literal without a backtracking regular expression.

    Full WeChat saves contain megabytes of minified code and CSS.  The former
    regex could backtrack across that code for a common key such as ``content``;
    it appeared as an indefinitely stuck parser.  This bounded linear scan only
    accepts a direct ``key: 'value'`` or ``key = 'value'`` assignment.
    """
    max_literal_length = 1_500_000
    start = 0
    while True:
        index = script.find(key, start)
        if index < 0:
            return ""
        start = index + len(key)
        if index and (script[index - 1].isalnum() or script[index - 1] in "_$"):
            continue
        end_key = index + len(key)
        if end_key < len(script) and (script[end_key].isalnum() or script[end_key] in "_$"):
            continue

        cursor = end_key
        if index and script[index - 1] in "\"'" and cursor < len(script) and script[cursor] == script[index - 1]:
            cursor += 1
        while cursor < len(script) and script[cursor].isspace():
            cursor += 1
        if cursor >= len(script) or script[cursor] not in ":=":
            continue
        cursor += 1
        while cursor < len(script) and script[cursor].isspace():
            cursor += 1
        if cursor >= len(script) or script[cursor] not in "\"'":
            continue

        quote = script[cursor]
        value_start = cursor + 1
        cursor = value_start
        escaped = False
        while cursor < len(script) and cursor - value_start <= max_literal_length:
            char = script[cursor]
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                return decode_js_string(script[value_start:cursor])
            cursor += 1
        return ""


def extract_metadata(root: Node) -> dict[str, str]:
    # Metadata used to walk the complete DOM separately for meta, title, link and
    # script tags.  A single pass keeps saved-page parsing predictable.
    metas: dict[str, str] = {}
    title_node = None
    canonical = ""
    scripts: list[str] = []
    for node in root.walk():
        if node.tag == "meta":
            key = (node.attrs.get("name") or node.attrs.get("property") or "").lower()
            value = node.attrs.get("content", "").strip()
            if key and value and key not in metas:
                metas[key] = value
        elif node.tag == "title" and title_node is None:
            title_node = node
        elif node.tag == "link" and not canonical and node.attrs.get("rel", "").lower() == "canonical":
            canonical = node.attrs.get("href", "")
        elif node.tag == "script":
            scripts.append("".join(child for child in node.children if isinstance(child, str)))

    def meta(*names: str) -> str:
        return next((metas[name.lower()] for name in names if name.lower() in metas), "")

    script = "\n".join(scripts)
    title = meta("og:title", "twitter:title")
    if not title and title_node is not None:
        title = visible_text(title_node)
    title = title or find_script_string(script, "msg_title")
    author = meta("author", "article:author") or find_script_string(script, "author") or find_script_string(script, "author_name")
    account = meta("og:site_name") or find_script_string(script, "nickname")
    url = meta("og:url", "twitter:url")
    if not url:
        url = canonical
    raw_time = meta("article:published_time", "publish_time", "date") or find_script_string(script, "publish_time")
    if not raw_time:
        raw_time = find_script_string(script, "create_time")
    return {"title": title, "author": author, "account": account, "url": url, "publish_time": normalize_time(raw_time)}


def normalize_time(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if value.isdigit() and len(value) >= 9:
        try:
            zone = dt.timezone(dt.timedelta(hours=8))
            return dt.datetime.fromtimestamp(int(value), tz=dt.timezone.utc).astimezone(zone).strftime("%Y-%m-%d %H:%M:%S %z")
        except (OverflowError, OSError, ValueError):
            return ""
    return value


def embedded_content_roots(root: Node) -> list[Node]:
    script = _script_text(root)
    result: list[Node] = []
    for key in ("content_noencode", "content"):
        content = find_script_string(script, key)
        if "<" in content and len(content) > 80:
            result.append(parse_html(content))
    return result
