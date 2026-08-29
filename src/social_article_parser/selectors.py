"""集中维护可观测、可扩展的正文候选选择器。"""

WECHAT_CONTENT_SELECTORS = (
    "#js_content",
    "#img-content",
    "#page-content",
    ".rich_media_content",
    ".rich_media_area_primary",
    ".rich_media_wrp",
    "article",
)

NOISE_TAGS = {"script", "style", "noscript", "svg", "iframe", "canvas", "template"}
NOISE_HINTS = (
    "advert", "ad_container", "recommend", "related", "comment", "footer", "toolbar",
    "share", "vote", "reward", "qr_code", "js_pc_qr_code", "like", "readmore",
    "weui", "copyright", "original_area",
)
CONTENT_TAGS = {"article", "main", "section", "div", "td"}
BLOCK_TAGS = {"p", "div", "section", "article", "main", "blockquote", "li", "figcaption", "h1", "h2", "h3", "h4", "h5", "h6"}
