"""Write a made-up data directory for screenshots and trying the UI.

    uv run python scripts/demo_data.py /tmp/fk-demo
    FK_DATA_DIR=/tmp/fk-demo FK_EMBED_MODEL= uv run fk rebuild

Every source, title and transcript here is fictional; covers are rendered gradients.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

NOW = datetime.now(timezone.utc).replace(microsecond=0)

SOURCES = [
    {"id": "yt-UCdemoNorthwindLab", "platform": "youtube", "channel_id": "UCdemoNorthwindLab",
     "url": "https://www.youtube.com/channel/UCdemoNorthwindLab", "name": "Northwind Lab", "colors": ("#1e3a8a", "#38bdf8")},
    {"id": "bili-10001", "platform": "bilibili", "mid": "10001", "url": "https://space.bilibili.com/10001",
     "name": "山野厨房", "colors": ("#7c2d12", "#fb923c")},
    {"id": "xhs-000000000000000000000001", "platform": "xiaohongshu", "user_id": "000000000000000000000001",
     "xsec_token": "demo", "url": "https://www.xiaohongshu.com/user/profile/000000000000000000000001",
     "name": "Mira 的书架", "colors": ("#831843", "#f9a8d4")},
    {"id": "pod-demolongsig", "platform": "podcast", "url": "https://example.com/long-signal.xml",
     "name": "The Long Signal", "colors": ("#14532d", "#86efac")},
    {"id": "rss-demofieldno", "platform": "rss", "url": "https://example.com/field-notes.xml",
     "name": "Field Notes", "colors": ("#3f3f46", "#d4d4d8")},
]
COLORS = {s["id"]: s.pop("colors") for s in SOURCES}

EP42_CUES = [
    "Welcome back to The Long Signal. Today we're talking about the telephone, and what its first years can teach us about new technology.",
    "When Bell's company offered the patent to Western Union, the answer was no. They saw it as a worse telegraph: no record, no wires to spare.",
    "So early telephone companies went looking for uses. One of the strangest was the theatrophone: you could dial into a concert hall and listen live.",
    "Think of it as nineteenth century streaming. Hotels in Paris had coin-operated receivers in the lobby, five minutes of opera for fifty centimes.",
    "Meanwhile people complained that the phone was ruining conversation. Newspapers mocked housewives who spent the afternoon chatting.",
    "But that complaint is the tell. When people use a tool for something its makers never planned, that's when it has really arrived.",
    "Let's bring this to today. General purpose technologies tend to look like toys or like worse versions of what came before.",
    "Electricity first replaced the steam engine in the same factory layout. The gains only came decades later when the factories were redesigned.",
    "The same is probably true of the language models everyone is arguing about. We're still in the bolt-it-onto-the-old-factory phase.",
    "One difference: the telephone did not improve itself. Whether that changes the story is the open question for the next decade.",
    "Before we go, a recommendation. The Switchboard Years is a short, readable history, and the chapter on operators is wonderful.",
    "That's it for this episode. Write to us with your own favorite forgotten use of an old technology.",
]

EP42_SUMMARY = """A history of the telephone's awkward first years, used as a lens on how general purpose technologies find their uses

- Western Union turned down the telephone patent because it looked like a worse telegraph
- Early companies tried odd uses such as the theatrophone, a dial-in concert line that worked like 19th century streaming
- Complaints about people chatting on the phone were a sign the tool had found real, unplanned uses
- New general purpose technologies first get bolted onto old workflows; the big gains arrive after the work itself is redesigned

## A worse telegraph [0:30](#t=30)

When Bell's company offered the patent, Western Union declined: the telephone left no written record and seemed to compete for the same wires. Nobody yet knew what it was for.

## Theatrophones and the search for a use [1:00](#t=60)

Telephone companies experimented widely. In Paris, hotel lobbies had coin-operated receivers wired to the opera, five minutes for fifty centimes, an early form of live streaming.

## When users take over [2:00](#t=120)

Newspapers mocked people who spent afternoons chatting. The hosts read that as the moment of arrival: people were using the phone for something its makers never planned.

## Lessons for today's AI [3:00](#t=180)

Electricity only paid off once factories were redesigned around it. Language models are probably still in the bolt-on phase. The open question is that, unlike the telephone, AI may improve itself.
"""

EP41_SUMMARY = """Why attention behaves like a shared pasture, and what communities have done to protect it

- Attention is rival and hard to exclude, the textbook definition of a commons
- Notification defaults are where most of the overgrazing happens
- Small groups that agreed on quiet hours reported calmer, more useful channels

## The pasture model [0:00](#t=0)

The hosts borrow Elinor Ostrom's work on shared resources and apply it to group chats and feeds.

## Rules that worked [9:00](#t=540)

Quiet hours, digest modes and a norm of replying in batches all came up as practical fixes.
"""

NW_SUMMARY = """Smaller language models are getting good enough for most everyday tasks, and they change where software runs

- A 3B model fine-tuned on one task often beats a general model 30 times its size on that task
- Running locally removes latency and per-request cost, which changes what features are worth building
- The trade-off is maintenance: someone has to own evaluation and updates

## Benchmarks versus real work [0:00](#t=0)

The video compares leaderboard scores with a set of real support tickets and finds the gap much smaller than the scores suggest.

## What local inference unlocks [8:20](#t=500)

Features that would be too expensive per call, such as summarizing every notification, become cheap enough to leave on.
"""

POT_SUMMARY = """开锅、养锅到日常保养的完整流程，一口铁锅用十年的关键是“干燥 + 薄油”

- 新锅先用高温烧掉出厂防锈层，再用猪皮或薄油反复擦锅
- 每次用完趁热冲洗，不用洗洁精，烧干后抹一层薄油
- 生锈不可怕：钢丝球擦掉锈迹后重新开锅即可

## 开锅 [0:40](#t=40)

大火把锅烧到发蓝，冷却后用肥猪皮在锅里反复擦，直到锅面形成一层均匀的黑色油膜。

## 日常保养 [5:10](#t=310)

炒完菜趁热用清水和竹刷冲洗，回到火上烧干水分，再用厨房纸抹一层薄油。
"""

ARTICLE_BODY = """A commonplace book is a notebook of things worth keeping: quotes, ideas, numbers, a recipe that worked.

## Why bother

Feeds are optimized for the next item. A commonplace book is optimized for the item you will want again in three years.

## How I keep mine

- One plain text file per month
- Every entry starts with where it came from
- Once a quarter I reread everything and move the best into topic pages

## What changed

I search my own notes before I search the web. Most of the time the answer is already there, with my own context attached.
"""


def iso(days, hours=0):
    return (NOW - timedelta(days=days, hours=hours)).isoformat()


def cues_from(lines, step=30):
    return [{"start": i * step, "end": (i + 1) * step, "text": text} for i, text in enumerate(lines)]


ITEMS = [
    # id, source, platform, kind, title, days ago, extra
    dict(id="pod-ep42longsig", source="pod-demolongsig", title="EP 42｜How Telephones Taught Us to Talk", days=1,
         duration=2410, format="audio", cues=EP42_CUES, summary=EP42_SUMMARY, method="asr",
         subtitle="A history of the telephone's awkward first years, used as a lens on how general purpose technologies find their uses",
         body="We trace the telephone from rejected patent to household habit, and ask what its first decades say about AI.\n\n"
              "**00:30 A worse telegraph**\n**01:00 Theatrophones**\n**03:00 Lessons for today**\n\nBook: The Switchboard Years"),
    dict(id="yt-nwsmallmodels", source="yt-UCdemoNorthwindLab", title="Why Small Models Are Eating the World", days=2,
         duration=1820, cues=["Today we put small models against big ones on real tasks."] * 6, summary=NW_SUMMARY,
         subtitle="Smaller language models are getting good enough for most everyday tasks, and they change where software runs"),
    dict(id="bili-BV1demoPot001", source="bili-10001", title="一口铁锅用十年：开锅与养锅全过程", days=2, duration=812,
         cues=["今天教大家开一口新铁锅。", "先大火把锅烧到发蓝。", "然后用肥猪皮反复擦。"], summary=POT_SUMMARY,
         subtitle="开锅、养锅到日常保养的完整流程，一口铁锅用十年的关键是“干燥 + 薄油”"),
    dict(id="xhs-6a00000000000000000000a1", source="xhs-000000000000000000000001", kind="note",
         title="今年读过最好的 5 本非虚构", days=3, format="note", transcript="n/a",
         body="1.《电话简史》\n2.《注意力公地》\n3.《慢互联网笔记》\n4.《铁锅与火候》\n5.《摘录本的艺术》\n每本都写了一句话短评，收藏慢慢看。"),
    dict(id="pod-ep41longsig", source="pod-demolongsig", title="EP 41｜Attention Is a Commons", days=6, duration=2105,
         format="audio", cues=["Attention is a shared pasture."] * 4, summary=EP41_SUMMARY, method="asr",
         subtitle="Why attention behaves like a shared pasture, and what communities have done to protect it",
         body="Elinor Ostrom, group chats and quiet hours."),
    dict(id="yt-nwlocalfirstq", source="yt-UCdemoNorthwindLab", title="Live: Q&A on Local-First Software", days=3,
         duration=3920, format="live", transcript="asr_running"),
    dict(id="bili-BV1demoBeef01", source="bili-10001", title="番茄牛腩的三个关键步骤", days=4, duration=520,
         cues=["牛腩先冷水下锅焯水。", "番茄分两次下。"]),
    dict(id="art-demofieldno01", source="rss-demofieldno", platform="article", kind="article",
         title="On Keeping a Commonplace Book", days=4, body=ARTICLE_BODY, transcript="n/a"),
    dict(id="yt-nwmarkdownnot", source="yt-UCdemoNorthwindLab", title="I Rebuilt My Note System in Plain Markdown",
         days=5, duration=945, cues=["Everything is a plain text file now."] * 3),
    dict(id="xhs-6a00000000000000000000a2", source="xhs-000000000000000000000001", title="通勤 40 分钟，我这样听完一本书",
         days=6, format="video", transcript="n/a", duration=95, body="地铁上听书的三个小技巧。"),
    dict(id="bili-BV1demoMkt001", source="bili-10001", title="凌晨四点的早市，我买了这些", days=7, duration=640,
         cues=["凌晨四点，早市已经很热闹了。"] * 3),
    dict(id="yt-nwcontextswit", source="yt-UCdemoNorthwindLab", title="The Hidden Cost of Context Switching", days=8,
         duration=58, format="short", cues=["Every switch costs you about twenty minutes."]),
    dict(id="pod-ep40longsig", source="pod-demolongsig", title="EP 40｜Notes From a Slow Internet", days=13, duration=1980,
         format="audio", transcript="n/a", body="What we gained and lost when pages took ten seconds to load."),
    dict(id="art-demofieldno02", source="rss-demofieldno", platform="article", kind="article",
         title="What I Learned From a Year Without Feeds", days=12, transcript="n/a",
         body="I unsubscribed from every feed for a year.\n\n## The first month\n\nMostly withdrawal.\n\n## After that\n\nI read fewer, longer things."),
    dict(id="xhs-6a00000000000000000000a3", source="xhs-000000000000000000000001", kind="note",
         title="书桌改造：从杂乱到专注", days=14, format="note", transcript="n/a",
         body="只留一盏灯、一本书和一支笔。"),
]

STATE = {
    "read": ["yt-nwmarkdownnot", "bili-BV1demoMkt001", "art-demofieldno02", "yt-nwcontextswit"],
    "later": ["yt-nwlocalfirstq", "art-demofieldno01"],
    "favorite": ["pod-ep42longsig", "bili-BV1demoPot001"],
    "summary_watch": ["pod-ep41longsig", "yt-nwlocalfirstq", "bili-BV1demoBeef01"],
}

THUMB_HTML = """<html><body style="margin:0">
<div style="width:640px;height:360px;display:flex;flex-direction:column;justify-content:flex-end;box-sizing:border-box;
padding:34px 38px;background:radial-gradient(circle at 80% 15%,{b}cc 0,transparent 55%),linear-gradient(135deg,{a},{b});
font-family:'Noto Sans CJK SC','PingFang SC',sans-serif;color:white">
<div style="font-size:18px;font-weight:700;letter-spacing:.08em;opacity:.8;text-transform:uppercase">{label}</div>
<div style="font-size:40px;line-height:1.15;font-weight:800;margin-top:10px;text-shadow:0 2px 12px #0004">{title}</div>
</div></body></html>"""


def render_thumbs(jobs):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 640, "height": 360})
        for path, html in jobs:
            page.set_content(html)
            page.screenshot(path=str(path), type="jpeg", quality=88)
        browser.close()


def main(target):
    root = Path(target).expanduser()
    if root.exists() and any(root.iterdir()):
        sys.exit(f"{root} is not empty")
    names = {s["id"]: s["name"] for s in SOURCES}
    for source in SOURCES:
        source.update(added_at=iso(30), removed=False, since=None, last_polled=iso(0, 2), last_error=None,
                      backfilled_at=iso(30))
    root.mkdir(parents=True, exist_ok=True)
    (root / "sources.yaml").write_text(yaml.safe_dump({"sources": SOURCES}, allow_unicode=True, sort_keys=False))
    (root / "state.json").write_text(json.dumps(STATE, ensure_ascii=False))
    thumbs = []
    for spec in ITEMS:
        source = next(s for s in SOURCES if s["id"] == spec["source"])
        platform = spec.get("platform") or source["platform"]
        prefix, native = spec["id"].split("-", 1)
        folder = root / "items" / platform / native
        folder.mkdir(parents=True)
        cues = cues_from(spec["cues"]) if spec.get("cues") else []
        transcript = spec.get("transcript") or ("ok" if cues else "none")
        meta = {
            "id": spec["id"], "platform": platform, "kind": spec.get("kind", "video"), "native_id": native,
            "source_id": source["id"], "title": spec["title"], "author": names[source["id"]],
            "url": source["url"], "published": iso(spec["days"], 3), "date_approx": False,
            "duration": spec.get("duration"), "format": spec.get("format", "video"), "thumbnail_url": None,
            "transcript": transcript, "backfill": False, "added_at": iso(spec["days"]),
        }
        if platform == "podcast":
            meta["audio_url"] = "https://example.com/audio.m4a"
        if spec.get("method") or cues:
            meta["transcript_method"] = spec.get("method", "subtitles")
        if spec.get("subtitle"):
            meta["subtitle"] = spec["subtitle"]
        if meta["kind"] == "article":
            meta.update(body_status="ok", site="example.com")
        head = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False)
        (folder / "item.md").write_text(f"---\n{head}---\n{spec.get('body', '').strip()}\n", encoding="utf-8")
        if cues:
            (folder / "transcript.json").write_text(json.dumps(cues, ensure_ascii=False))
            (folder / "transcript.txt").write_text("\n".join(c["text"] for c in cues) + "\n")
        if spec.get("summary"):
            (folder / "summary.md").write_text(spec["summary"])
        a, b = COLORS[source["id"]]
        thumbs.append((folder / "thumb.jpg", THUMB_HTML.format(a=a, b=b, label=names[source["id"]], title=spec["title"])))
    render_thumbs(thumbs)
    print(f"wrote {len(ITEMS)} items from {len(SOURCES)} sources to {root}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/fk-demo")
