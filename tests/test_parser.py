from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from social_article_parser import ArticleParser
from social_article_parser.dom import HTMLTooLargeError


FIXTURES = Path(__file__).parent / "fixtures"


class ArticleParserTests(unittest.TestCase):
    def parse_fixture(self, category: str):
        html = (FIXTURES / category / "article.html").read_text(encoding="utf-8")
        return ArticleParser().parse(html)

    def test_normal_article_preserves_structure_and_filters_noise(self):
        document, metadata, _ = self.parse_fixture("normal_article")
        self.assertEqual(metadata.title, "在雨中读一座城")
        self.assertEqual(metadata.extractor, "wechat_dom:#js_content")
        self.assertEqual(metadata.status, "ok")
        self.assertIn("## 清晨的街道", document)
        self.assertIn("- 第一条观察", document)
        self.assertIn("> 城市并不急着回答问题。", document)
        self.assertIn("[图片：雨后街景]", document)
        self.assertNotIn("推荐阅读", document)

    def test_script_embedded_content_is_decoded_without_duplication(self):
        document, metadata, _ = self.parse_fixture("old_article")
        self.assertEqual(metadata.extractor, "wechat_embedded_article_data")
        self.assertIn("旧版文章也应保留完整段落", document)
        self.assertEqual(document.count("旧版文章也应保留完整段落"), 1)
        self.assertIn("# 旧版存档", document)

    def test_malformed_page_returns_visible_low_confidence(self):
        document, metadata, candidate = self.parse_fixture("malformed")
        self.assertEqual(metadata.status, "low_confidence")
        self.assertTrue(metadata.reasons)
        self.assertTrue(candidate)
        self.assertIn("内容没有足够的结构线索", document)

    def test_metadata_is_json_serializable(self):
        _, metadata, _ = self.parse_fixture("normal_article")
        data = json.loads(json.dumps(metadata.to_dict(), ensure_ascii=False))
        self.assertEqual(data["image_count"], 1)

    def test_wechat_section_span_paragraphs_are_preserved(self):
        html = """
        <div id="js_content">
          <section><span>第一段由 section 和 span 组成，不应被遗漏。</span></section>
          <section><span>第二段同样需要保留。</span></section>
        </div>
        """
        document, metadata, _ = ArticleParser().parse(html)
        self.assertEqual(metadata.extractor, "wechat_dom:#js_content")
        self.assertIn("第一段由 section 和 span 组成", document)
        self.assertIn("第二段同样需要保留", document)

    def test_pathologically_deep_html_is_rejected_early(self):
        html = "<div>" * 600 + "正文" + "</div>" * 600
        with self.assertRaises(HTMLTooLargeError):
            ArticleParser().parse(html)


if __name__ == "__main__":
    unittest.main()
