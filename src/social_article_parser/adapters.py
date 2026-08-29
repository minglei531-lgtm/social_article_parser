"""可扩展的来源适配器接口。

每个社媒只负责提供自己的正文容器和内嵌字段；评分、清洗、输出由公共解析器统一完成。
后续新增平台时，实现 SourceAdapter 并加入 DEFAULT_ADAPTERS 即可。
"""

from __future__ import annotations

from typing import Protocol

from .dom import Node, matches, parse_html
from .metadata import embedded_content_roots
from .models import Candidate
from .selectors import WECHAT_CONTENT_SELECTORS


class SourceAdapter(Protocol):
    name: str

    def candidates(self, root: Node) -> list[Candidate]:
        """返回该来源特有的正文候选；没有命中时返回空列表。"""


class WeChatAdapter:
    name = "wechat"

    def candidates(self, root: Node) -> list[Candidate]:
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


DEFAULT_ADAPTERS: tuple[SourceAdapter, ...] = (WeChatAdapter(),)
