from typing import Literal

from mcp.server.mcpserver import MCPServer

from fkslop import search as retrieval
from fkslop import store

INSTRUCTIONS = """用户自建媒体站的资料库：只收录用户指定来源（YouTube 频道、B 站 UP 主、小红书博主、RSS 文章、播客）的视频与播客逐字稿和文章。
小红书笔记只收标题、简介和链接；视频笔记只有手动提取过才有逐字稿。播客单集带节目简介，只有打开或总结过的才有逐字稿。
逐字稿来自平台字幕或本地语音识别，可能有识别错误；summary 是 AI 生成的，不是作者原话。
用户收藏的条目是其精选内容，search / list_items 传 favorites_only=true 可只查收藏。
引用时给出标题、作者、日期和返回的 url（视频链接已带时间点）。只读，不能添加或修改内容。"""

server = MCPServer(name="fk-ai-slop", instructions=INSTRUCTIONS)


def _favorites():
    return set(store.load_state().get("favorite") or [])


@server.tool()
def search(query: str | None = None, author: str | None = None, source: str | None = None,
           platform: Literal["youtube", "bilibili", "xiaohongshu", "article", "podcast"] | None = None, title: str | None = None,
           date_from: str | None = None, date_to: str | None = None,
           mode: Literal["semantic", "keyword"] = "semantic", top_k: int = 10,
           favorites_only: bool = False) -> list[dict]:
    """检索资料库。

    query 为空时按元数据列出条目（按日期倒序）。mode=semantic 做向量语义检索；mode=keyword 匹配标题和原文
    （3 字以上走全文索引）。author / source / title 为子串匹配（source 也可填来源 ID），date_from / date_to
    形如 2026-01 或 2026-01-31。每个条目最多返回 2 个片段，top_k 最大 50。favorites_only=true 只查用户收藏的条目。
    返回的 item_id + chunk 可交给 get_item(around_chunk=...) 读取上下文。
    """
    return retrieval.search(query, author, source, platform, title, date_from, date_to, mode, top_k,
                            item_ids=_favorites() if favorites_only else None)


@server.tool()
def list_items(source: str | None = None, author: str | None = None,
               platform: Literal["youtube", "bilibili", "xiaohongshu", "article", "podcast"] | None = None, title: str | None = None,
               date_from: str | None = None, date_to: str | None = None,
               limit: int = 20, offset: int = 0, favorites_only: bool = False) -> list[dict]:
    """按元数据列出条目，按发布日期倒序。transcript 字段表示逐字稿状态（ok 才有可读正文）。
    favorites_only=true 只列用户收藏的条目。"""
    rows = retrieval.list_items(author=author, source=source, platform=platform, title=title,
                                date_from=date_from, date_to=date_to, limit=min(limit, 200), offset=offset,
                                only_ids=_favorites() if favorites_only else None)
    keep = ("id", "title", "author", "platform", "source_id", "url", "published", "duration", "transcript")
    return [{k: row[k] for k in keep} for row in rows]


@server.tool()
def list_sources() -> list[dict]:
    """列出所有订阅来源（含已删除来源，其内容仍可检索）。"""
    return [{k: s.get(k) for k in ("id", "platform", "name", "url", "removed", "last_polled")}
            for s in store.load_sources()]


@server.tool()
def get_item(id: str, part: Literal["summary", "transcript", "full"] = "summary",
             around_chunk: int | None = None, offset_chunk: int = 0, limit_chunks: int = 12) -> dict:
    """读取一个条目。

    part=summary 返回元数据和 AI 总结；part=transcript 按切块分页返回逐字稿（带起始秒数和带时间点的链接，
    用 next_offset_chunk 翻页）；part=full 对文章返回全文 Markdown，对视频等同 transcript。
    around_chunk 指定时返回该切块前后各 2 块。
    """
    return retrieval.get_item(id, part, around_chunk, 2, offset_chunk, min(limit_chunks, 40))


def main():
    server.run("stdio")


if __name__ == "__main__":
    main()
