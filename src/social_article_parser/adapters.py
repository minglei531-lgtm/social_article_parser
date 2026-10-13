"""可扩展的来源适配器接口。

每个社媒只负责提供自己的正文容器和内嵌字段；评分、清洗、输出由公共解析器统一完成。
后续新增平台时，实现 SourceAdapter 并加入 DEFAULT_ADAPTERS 即可。
"""

from __future__ import annotations

import json
import re
from typing import Protocol

from .dom import Node, matches, parse_html
from .metadata import embedded_content_roots
from .models import Candidate
from .selectors import WECHAT_CONTENT_SELECTORS


class SourceAdapter(Protocol):
    name: str

    def candidates(self, root: Node) -> list[Candidate]:
        """返回该来源特有的正文候选；没有命中时返回空列表。"""


def _is_zhihu_answer_page(root: Node) -> bool:
    has_initial_data = False
    has_answer_item = False
    for node in root.walk():
        if node.tag == "script" and node.attrs.get("id") == "js-initialData":
            has_initial_data = True
        if "AnswerItem" in node.attrs.get("class", "").split() and node.attrs.get("name", "").isdigit():
            has_answer_item = True
        if node.tag == "meta":
            key = (node.attrs.get("property") or node.attrs.get("name") or "").lower()
            url = node.attrs.get("content", "")
            if key in {"og:url", "twitter:url"} and "zhihu.com" in url and "/answer/" in url:
                return True
        if has_initial_data and has_answer_item:
            return True
    return False


class WeChatAdapter:
    name = "wechat"

    def candidates(self, root: Node) -> list[Candidate]:
        # Zhihu stores its answer body in a JSON field named ``content`` too.
        # Do not let WeChat's old-page script fallback claim that body.
        if _is_zhihu_answer_page(root):
            return []
        result: list[Candidate] = []
        # All selectors are simple tag/id/class checks.  Scan the tree once rather
        # than once per selector; large saved pages can otherwise be very costly.
        for node in root.walk():
            for selector in WECHAT_CONTENT_SELECTORS:
                if matches(node, selector):
                    result.append(Candidate(f"wechat_dom:{selector}", node))
        # Embedded JavaScript is a legacy fallback.  Modern WeChat saves already
        # have #js_content; scanning large page scripts in that case wastes time.
        if not result:
            for node in embedded_content_roots(root):
                result.append(Candidate("wechat_embedded_article_data", node))
        return result


class ZhihuAdapter:
    """Extract the primary answer from a saved Zhihu answer page.

    Zhihu's rendered page often shows only a short preview behind an
    ``阅读全文`` control.  The complete answer is normally included in the
    ``js-initialData`` JSON payload, so use that payload before considering
    rendered RichText nodes.
    """

    name = "zhihu"

    def candidates(self, root: Node) -> list[Candidate]:
        answer_id = self._answer_id(root)
        embedded = self._initial_answer_content(root, answer_id)
        if embedded:
            return [Candidate("zhihu_initial_answer_data", parse_html(embedded))]

        # Fallback for pages saved without js-initialData. Restrict the search to
        # AnswerItem cards so a large sidebar or recommended-content block cannot
        # become the selected article.
        result: list[Candidate] = []
        for node in root.walk():
            if not self._has_class(node, "RichText") or not self._inside_answer_item(node):
                continue
            if answer_id and self._inside_target_answer(node, answer_id):
                return [Candidate("zhihu_dom:primary_answer", node)]
            result.append(Candidate("zhihu_dom:answer_preview", node))
        return result

    @staticmethod
    def _has_class(node: Node, class_name: str) -> bool:
        return class_name in node.attrs.get("class", "").split()

    @staticmethod
    def _answer_id(root: Node) -> str:
        # Full saved pages carry this in og:url. A body-only clipboard fragment
        # does not, so fall back to Zhihu's primary AnswerItem marker below.
        for node in root.walk():
            if node.tag != "meta":
                continue
            key = (node.attrs.get("property") or node.attrs.get("name") or "").lower()
            if key not in {"og:url", "twitter:url"}:
                continue
            match = re.search(r"/answer/(\d+)", node.attrs.get("content", ""))
            if match:
                return match.group(1)

        answer_items = [
            node for node in root.walk()
            if "AnswerItem" in node.attrs.get("class", "").split() and node.attrs.get("name", "").isdigit()
        ]
        for node in answer_items:
            if node.attrs.get("itemprop") == "mainEntityOfPage":
                return node.attrs["name"]
        # The first answer card is the primary answer in Zhihu's body-only
        # clipboard output when the semantic itemprop has been stripped.
        return answer_items[0].attrs["name"] if answer_items else ""

    @staticmethod
    def _script_value(root: Node, script_id: str) -> str:
        for node in root.walk():
            if node.tag == "script" and node.attrs.get("id") == script_id:
                return "".join(child for child in node.children if isinstance(child, str))
        return ""

    def _initial_answer_content(self, root: Node, answer_id: str) -> str:
        if not answer_id:
            return ""
        raw = self._script_value(root, "js-initialData")
        if not raw:
            return ""
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return ""
        for value in self._walk_json(payload):
            if not isinstance(value, dict) or str(value.get("id", "")) != answer_id:
                continue
            content = value.get("content")
            if isinstance(content, str) and len(content) >= 40:
                return content
        return ""

    @staticmethod
    def _walk_json(value: object):
        stack = [value]
        while stack:
            current = stack.pop()
            yield current
            if isinstance(current, dict):
                stack.extend(current.values())
            elif isinstance(current, list):
                stack.extend(current)

    def _inside_answer_item(self, node: Node) -> bool:
        current = node.parent
        while current:
            if self._has_class(current, "AnswerItem"):
                return True
            current = current.parent
        return False

    def _inside_target_answer(self, node: Node, answer_id: str) -> bool:
        current = node.parent
        while current:
            if current.attrs.get("name") == answer_id:
                return True
            current = current.parent
        return False


# Zhihu's initial JSON also contains a generic ``content`` key.  Check its
# page-specific answer identifier first so WeChat's legacy script fallback does
# not claim a Zhihu answer merely because of that shared field name.
DEFAULT_ADAPTERS: tuple[SourceAdapter, ...] = (ZhihuAdapter(), WeChatAdapter(),)
