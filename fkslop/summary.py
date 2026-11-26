import json
import re

from fkslop import config, store
from fkslop.platforms import net

PROMPT = """你是认真的编辑，为一个只给自己看的阅读站写中文总结。读者想读完总结就判断是否值得看原视频/原文，或者直接获得主要内容。

只依据给出的材料，不补充材料外的事实。保留具体的数字、名字、论证和例子，不写空泛评价。逐字稿可能有自动识别错误，按上下文理解。

输出 JSON：
{
  "subtitle": "一句话说清这期讲了什么（中文，不超过 60 字）",
  "points": ["3 到 5 条要点，每条一句"],
  "sections": [{"heading": "小标题", "start": 该段内容在视频中开始的秒数（整数；文章填 null）, "text": "一到三段正文"}]
}
sections 按材料顺序，覆盖全部主要内容，一般 4 到 10 段。"""

MAX_CHARS = 150_000


def _clock(seconds):
    seconds = int(seconds or 0)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def material(meta, body, cues):
    if cues:
        lines, mark = [], -60
        for cue in cues:
            if cue["start"] - mark >= 60:
                lines.append(f"\n[{int(cue['start'])}s]")
                mark = cue["start"]
            lines.append(cue["text"])
        text = " ".join(lines)
    else:
        text = body
    head = f"标题：{meta.get('title')}\n作者：{meta.get('author')}\n日期：{meta.get('published')}\n\n"
    return head + text[:MAX_CHARS]


def call_model(content):
    if not config.LLM_ENABLED:
        raise RuntimeError("没有配置大模型：设置 FK_LLM_BASE_URL 和 FK_LLM_MODEL")
    headers = {"Authorization": "Bearer " + config.LLM_API_KEY} if config.LLM_API_KEY else {}
    with net.http_client() as client:
        response = client.post(
            config.LLM_BASE_URL.rstrip("/") + "/chat/completions",
            headers=headers,
            json={"model": config.LLM_MODEL, "max_tokens": 4000, "response_format": {"type": "json_object"},
                  "messages": [{"role": "system", "content": PROMPT}, {"role": "user", "content": content}],
                  **config.LLM_EXTRA_BODY},
            timeout=300,
        )
        response.raise_for_status()
    raw = response.json()["choices"][0]["message"].get("content") or ""
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    return json.loads(raw)


def to_markdown(data):
    lines = [data.get("subtitle", "").strip(), ""]
    lines += [f"- {p.strip()}" for p in data.get("points") or []
              if isinstance(p, str) and len(p.strip()) > 4 and p.strip() not in ("subtitle", "points", "sections")]
    for section in data.get("sections") or []:
        heading = section.get("heading", "").strip()
        start = section.get("start")
        if isinstance(start, (int, float)):
            heading += f" [{_clock(start)}](#t={int(start)})"
        lines += ["", f"## {heading}", "", section.get("text", "").strip()]
    return "\n".join(lines).strip() + "\n"


def summarize(iid):
    meta, body = store.read_item(iid)
    cues = store.read_transcript(iid)
    if not cues and not body.strip():
        raise RuntimeError("没有逐字稿或正文，无法总结")
    data = call_model(material(meta, body, cues))
    store.write_summary(iid, to_markdown(data))
    store.update_item(iid, subtitle=data.get("subtitle"))
