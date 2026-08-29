from __future__ import annotations

import re
from dataclasses import dataclass, field
from html import escape, unescape
from html.parser import HTMLParser
from typing import Iterator

from .selectors import BLOCK_TAGS, NOISE_HINTS, NOISE_TAGS


@dataclass
class Node:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list["Node | str"] = field(default_factory=list)
    parent: "Node | None" = None

    def walk(self) -> Iterator["Node"]:
        stack = [self]
        while stack:
            node = stack.pop()
            yield node
            stack.extend(child for child in reversed(node.children) if isinstance(child, Node))


class HTMLTooLargeError(ValueError):
    """Raised before an unusually large saved page can monopolize the computer."""


class TolerantHTMLTree(HTMLParser):
    """A small, tolerant DOM builder for saved (sometimes malformed) HTML."""

    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    MAX_NODES = 80_000
    MAX_DEPTH = 512
    MAX_SCRIPT_CHARS = 400_000

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("document")
        self.stack = [self.root]
        self.node_count = 1
        self._script_chars = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        self.node_count += 1
        if self.node_count > self.MAX_NODES:
            raise HTMLTooLargeError("HTML 标签过多（超过 80,000 个）。请先用浏览器“另存为仅 HTML”后再试。")
        if len(self.stack) > self.MAX_DEPTH:
            raise HTMLTooLargeError("HTML 嵌套过深（超过 512 层）。已停止解析以保护电脑。")
        node = Node(tag, {k.lower(): v or "" for k, v in attrs}, parent=self.stack[-1])
        self.stack[-1].children.append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if data:
            # Archive pages often embed megabytes of analytics JavaScript.  It is
            # not article content; retaining all of it makes both parsing and the
            # metadata regex unnecessarily expensive.  Keep a small bounded slice
            # for legacy WeChat content embedded in a script.
            if self.stack[-1].tag == "script":
                remaining = self.MAX_SCRIPT_CHARS - self._script_chars
                if remaining <= 0:
                    return
                data = data[:remaining]
                self._script_chars += len(data)
            self.stack[-1].children.append(data)

    def handle_comment(self, data: str) -> None:
        pass


def parse_html(html: str) -> Node:
    if len(html) > 8_000_000:
        raise HTMLTooLargeError("HTML 超过 8 MB，已停止解析以保护电脑。请先删除脚本、图片数据或无关页面内容。")
    parser = TolerantHTMLTree()
    parser.feed(html)
    parser.close()
    return parser.root


def matches(node: Node, selector: str) -> bool:
    if selector.startswith("#"):
        return node.attrs.get("id") == selector[1:]
    if selector.startswith("."):
        return selector[1:] in node.attrs.get("class", "").split()
    return node.tag == selector.lower()


def select(root: Node, selector: str) -> list[Node]:
    return [node for node in root.walk() if matches(node, selector)]


def attr_blob(node: Node) -> str:
    return " ".join((node.attrs.get("id", ""), node.attrs.get("class", ""))).lower()


def is_noise(node: Node) -> bool:
    if node.tag in NOISE_TAGS:
        return True
    blob = attr_blob(node)
    return any(hint in blob for hint in NOISE_HINTS)


def visible_text(node: Node) -> str:
    parts: list[str] = []
    stack: list[tuple[Node | str, bool]] = [(node, False)]
    leading_break_tags = {"br", "p", "div", "section", "li", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6"}
    while stack:
        current, closing = stack.pop()
        if isinstance(current, str):
            parts.append(current)
            continue
        if is_noise(current):
            continue
        if closing:
            if current.tag in BLOCK_TAGS:
                parts.append("\n")
            continue
        if current.tag in leading_break_tags:
            parts.append("\n")
        stack.append((current, True))
        stack.extend((child, False) for child in reversed(current.children))
    return normalize_text("".join(parts))


def text_lengths(root: Node) -> dict[int, int]:
    """Return visible text lengths for every node in one bottom-up traversal."""
    lengths: dict[int, int] = {}
    stack: list[tuple[Node, bool]] = [(root, False)]
    while stack:
        node, visited = stack.pop()
        if is_noise(node):
            lengths[id(node)] = 0
            continue
        if not visited:
            stack.append((node, True))
            stack.extend((child, False) for child in node.children if isinstance(child, Node))
            continue
        lengths[id(node)] = sum(
            len(child) if isinstance(child, str) else lengths[id(child)]
            for child in node.children
        )
    return lengths


def normalize_text(value: str) -> str:
    value = unescape(value).replace("\xa0", " ").replace("\r", "")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r" *\n *", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def serialize(node: Node | str) -> str:
    if isinstance(node, str):
        return escape(node, quote=False)
    if node.tag == "document":
        return "".join(serialize(child) for child in node.children)
    attrs = "".join(f' {key}="{escape(value, quote=True)}"' for key, value in node.attrs.items())
    if node.tag in TolerantHTMLTree.VOID:
        return f"<{node.tag}{attrs}>"
    return f"<{node.tag}{attrs}>" + "".join(serialize(child) for child in node.children) + f"</{node.tag}>"


def markdown_from_node(root: Node) -> tuple[str, int]:
    """Render semantic article markup without exposing tracking URLs or page chrome."""
    lines: list[str] = []
    image_count = 0

    def inline(node: Node | str) -> str:
        nonlocal image_count
        if isinstance(node, str):
            return node
        if is_noise(node):
            return ""
        if node.tag == "br":
            return "\n"
        if node.tag == "img":
            image_count += 1
            label = normalize_text(node.attrs.get("alt", "") or node.attrs.get("title", ""))
            return f"[图片：{label}]" if label else "[图片]"
        value = "".join(inline(child) for child in node.children)
        if node.tag in {"strong", "b"} and value.strip():
            return f"**{value.strip()}**"
        if node.tag in {"em", "i"} and value.strip():
            return f"*{value.strip()}*"
        return value

    def append_block(value: str) -> None:
        value = normalize_text(value)
        if value:
            lines.append(value)

    def visit(node: Node | str, list_depth: int = 0) -> None:
        if isinstance(node, str) or is_noise(node):
            return
        if node.tag == "img":
            append_block(inline(node))
            return
        if node.tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            append_block("#" * int(node.tag[1]) + " " + inline(node))
            return
        if node.tag == "blockquote":
            text = normalize_text(inline(node))
            if text:
                lines.append("\n".join("> " + line for line in text.splitlines()))
            return
        if node.tag in {"ul", "ol"}:
            ordered = node.tag == "ol"
            item_number = 1
            for child in node.children:
                if isinstance(child, Node) and child.tag == "li":
                    prefix = f"{item_number}. " if ordered else "- "
                    append_block("  " * list_depth + prefix + inline(child))
                    item_number += 1
            return
        if node.tag in {"p", "figcaption"}:
            append_block(inline(node))
            return
        # Recent WeChat pages often use a stack of <section><span>...</span>
        # elements instead of <p>.  The old renderer descended into those spans
        # but ignored their text nodes, leaving only headings and lists.  Treat a
        # wrapper with no structural child as one normal paragraph.
        structural_tags = {
            "article", "main", "div", "section", "p", "figcaption",
            "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "ul", "ol",
        }
        has_structural_child = any(
            isinstance(child, Node) and child.tag in structural_tags
            for child in node.children
        )
        if not has_structural_child:
            append_block(inline(node))
            return
        for child in node.children:
            visit(child, list_depth + (1 if node.tag == "li" else 0))

    visit(root)
    # Consecutive duplicate blocks often occur in the DOM plus hidden display copies.
    deduped: list[str] = []
    for line in lines:
        if not deduped or normalize_for_compare(line) != normalize_for_compare(deduped[-1]):
            deduped.append(line)
    # Generic fallback nodes are sometimes a single unwrapped text block. Preserve it
    # instead of returning an empty document merely because it has no <p> children.
    if not deduped:
        fallback = visible_text(root)
        if fallback:
            deduped.append(fallback)
    return "\n\n".join(deduped).strip(), image_count


def normalize_for_compare(value: str) -> str:
    return re.sub(r"\W+", "", value).lower()
