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

    def test_zhihu_initial_data_wins_over_collapsed_dom_preview(self):
        answer_id = "2083961731395613124"
        full_content = (
            "<p>这是初始数据中的完整第一段，长度足以证明没有使用页面预览，而且其中保留了完整的自然语言内容。</p>"
            "<p>这是完整第二段，应该在解析结果里保留，也不应该被页面上的阅读全文控件截断。</p>"
            "<p>这是完整第三段，用来模拟一篇具有正常篇幅和多个段落结构的知乎回答正文。</p>"
        )
        payload = json.dumps({
            "initialState": {
                "entities": {"answers": {answer_id: {"id": answer_id, "content": full_content}}}
            }
        }, ensure_ascii=False)
        html = f"""
        <html><head>
          <title>示例回答 - 知乎</title>
          <meta property="og:url" content="https://www.zhihu.com/question/1/answer/{answer_id}">
        </head><body>
          <div class="ContentItem AnswerItem" name="{answer_id}">
            <span class="RichText"><p>这是 DOM 中被折叠的简短预览。</p></span>
            <button>阅读全文</button>
          </div>
          <script id="js-initialData" type="text/json">{payload}</script>
        </body></html>
        """
        document, metadata, _ = ArticleParser().parse(html)
        self.assertEqual(metadata.extractor, "zhihu_initial_answer_data")
        self.assertIn("完整第一段", document)
        self.assertIn("完整第二段", document)
        self.assertNotIn("被折叠的简短预览", document)

    def test_zhihu_body_fragment_uses_primary_answer_item(self):
        answer_id = "2016066411118731732"
        other_id = "2010122451300935122"
        full_content = (
            "<p>这是仅保留 body 时仍应提取的完整知乎正文第一段，不能因为移除了 head 元数据而变成短预览。</p>"
            "<p>第二段也必须保留，以验证目标回答 ID 来自页面的主实体标记。</p>"
        )
        payload = json.dumps({
            "initialState": {
                "entities": {"answers": {
                    answer_id: {"id": answer_id, "content": full_content},
                    other_id: {"id": other_id, "content": "<p>不应选中这条相关回答。</p>"},
                }}
            }
        }, ensure_ascii=False)
        html = f"""
        <body>
          <div class="ContentItem AnswerItem" name="{answer_id}" itemprop="mainEntityOfPage">
            <span class="RichText"><p>被折叠的首答预览。</p></span>
          </div>
          <div class="ContentItem AnswerItem" name="{other_id}">
            <span class="RichText"><p>相关回答预览。</p></span>
          </div>
          <script id="js-initialData" type="text/json">{payload}</script>
        </body>
        """
        document, metadata, _ = ArticleParser().parse(html)
        self.assertEqual(metadata.extractor, "zhihu_initial_answer_data")
        self.assertIn("完整知乎正文第一段", document)
        self.assertNotIn("不应选中", document)

    def test_pathologically_deep_html_is_rejected_early(self):
        html = "<div>" * 600 + "正文" + "</div>" * 600
        with self.assertRaises(HTMLTooLargeError):
            ArticleParser().parse(html)


if __name__ == "__main__":
    unittest.main()
