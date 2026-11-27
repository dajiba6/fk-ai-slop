# fk_ai_slop 设计

自用媒体站：只收指定来源的内容，Substack 式排版。站内内容同时是一份可检索的个人资料库，通过只读 MCP 提供给 Agent。

## 范围

- 来源：YouTube 频道、B 站 UP 主、小红书博主、RSS 文章源、播客 RSS；另可手动投递单条链接。不做排除规则（Shorts、直播照收）。
- 单用户：一个进程（systemd 用户服务）同时提供网站、后台任务和 MCP，默认端口 8090。访客只读，管理操作需要 `ADMIN_KEY`。
- 外部工具全部可选：没配大模型就没有 AI 总结，没配语音识别就只用平台字幕，没有 Ollama 就只有关键词搜索，没有小红书容器就不能加小红书来源。配置见 `.env.example`。

## 数据

数据目录在项目外（`FK_DATA_DIR`，默认 `~/media-archive`），文件是唯一真实来源；SQLite 索引可随时删掉重建。

```text
sources.yaml                      来源列表（网页管理页会写回）
state.json                        已看 / 稍后看 / 收藏
items/<platform>/<native_id>/
  item.md                         YAML 头（元数据、逐字稿状态）+ 正文（文章 Markdown 或视频简介）
  transcript.json                 [{start, end, text}]，秒
  transcript.txt                  纯文本
  summary.md                      按需生成的 AI 总结
  thumb.jpg                       本地缩略图
index.sqlite3                     派生：元数据、FTS5(trigram)、sqlite-vec、任务队列
favorites/<日期>_<作者>_<标题>_<条目 ID>.md
                                  派生：收藏条目的完整 Markdown（YAML 头 + AI 总结 + 简介/正文 + 带时间点链接的逐字稿），给 agent 当上下文
```

收藏导出：收藏 / 取消收藏时写入或删除对应文件，逐字稿、转写、正文、总结更新后重写；`favorited_at` 记首次导出时间并在重写时保留。`fk favorites` 按 `state.json` 整体重建。MCP 的 `search` / `list_items` 支持 `favorites_only`。

条目 ID：`yt-<id>`、`bili-<BV>`、`xhs-<笔记 ID>`、`art-<url 哈希>`。删除来源只在 `sources.yaml` 标 `removed: true`：停止抓取、不进首页，内容与检索保留。

## 代码结构

```text
fkslop/
  config.py          环境变量 / .env；外部工具没配就关掉对应功能
  platforms/         只负责和外部网站打交道，不碰索引
    net.py           HTTP 客户端、代理 / 直连 / IPv4 规则、yt-dlp 调用、下载
    youtube.py       频道解析、RSS 轮询、频道页回填、精确发布时间
    bilibili.py      UP 主空间投稿接口（WBI 签名）
    xiaohongshu.py   笔记解析、主页（xiaohongshu-mcp 容器 + Playwright 滚动）
    feeds.py         RSS / Atom、播客、网页正文提取
    media.py         单个视频：元数据、字幕轨道、音频下载
  pipeline.py        任务入口（加来源、投递、按需转写 / 总结）和各任务的处理函数
  worker.py          按 lane 串行执行任务队列
  store.py           数据目录里的文件读写（唯一真实来源）
  db.py / indexer.py / search.py / chunking.py   派生索引、切块与检索
  summary.py         调用大模型生成总结
  favorites.py       收藏导出 Markdown
  asr_worker.py      在语音识别 venv 里运行的 SenseVoice 脚本
  mcp_server.py / web/app.py / cli.py
```

来源平台模块统一提供 `resolve(url) -> source` 和 `poll(source, backfill) -> entries`，`platforms.SOURCES` 按平台名查表，新增平台只要加一个模块并登记。

## 抓取

- `fk poll`（systemd 定时器每 6 小时）为每个来源入队一个轮询任务，由网站进程内的后台 worker 执行。
- 起始日期：每个来源有 `since`（默认添加当年 1 月 1 日，空表示不限），早于它发布的内容不建条目、不抓封面和字幕。YouTube 回填的近似日期是上界，落在起始日期后一个月内的会查一次精确日期。在管理页改起始日期会清掉 `backfilled_at` 并重新回填，已有条目保留。
- 首次回填只做一次（记 `backfilled_at`）；之后的轮询只看最新一页（YouTube RSS 约 15 条，B 站 30 条），不会回头补旧内容。
- YouTube：日常轮询用频道 RSS（精确日期）；新来源回填用 `yt-dlp --flat-playlist` 列出 videos / shorts / streams，最多 1000 条，日期为近似值，抓到逐字稿时用视频元数据修正。
- B 站：空间投稿接口（WBI 签名，可选 `FK_BILIBILI_COOKIES` 登录 cookie），限速翻页，最多 1000 条。
- 小红书：只收链接（标题、封面、简介、发布时间），不自动下载视频、不自动做逐字稿。详情页可手动“提取逐字稿”（视频笔记：yt-dlp 直连下载音频后本地语音识别）和“生成总结”（用逐字稿，没有就用简介）。链接用 App 认的 `/discovery/item/<id>?xsec_token=…&xsec_source=app_share`（`/explore/` 只会打开 App 首页），管理员打开详情页即标记已看。博主主页要登录才能看，由 Docker 容器 [xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp)（无头浏览器 + 扫码登录的 cookie，`127.0.0.1:18060`）打开主页读 `__INITIAL_STATE__`，日常轮询只拿首屏约 60 条。首次回填（含改起始日期后的重新回填）用本机 Playwright 无头 Chromium 带上容器的登录 cookie（`FK_XHS_COOKIES`）滚动主页，直到笔记早于起始日期，页面会把加载出的笔记累积在 `__INITIAL_STATE__` 里。添加来源贴博主任意一条笔记或主页的分享链接：主页请求必须带该博主的一个有效 `xsec_token`，每次轮询后换成最新笔记的 token。发布时间取笔记 ID 前 8 位十六进制（Unix 时间戳）。单条笔记的分享页不登录也能解析（手机 UA）。
- RSS：只取 feed 自带条目；正文优先用 feed 全文，否则 trafilatura 抓网页转 Markdown。
- 播客：添加 RSS 时，前 10 条里有音频附件就当播客来源（`pod-…`）。单集存标题、时长、封面、节目简介和音频直链（`audio_url`），逐字稿初始为 `n/a`；管理员打开详情页或点“生成总结”时才下载音频做本地语音识别。详情页用 `<audio>` 播放，逐字稿和总结的时间点可跳转。小宇宙没有 RSS，用苹果播客 / 喜马拉雅等平台公开的 feed 地址。
- 逐字稿：yt-dlp 只下载字幕轨道，每个平台约 30 秒一条，从新到旧。YouTube 按 `FK_YOUTUBE_SUB_LANGS` 请求中文和英文，但优先口播的中文（人工字幕，或没有 `tlang` 的自动字幕 / `-orig`），跳过 YouTube 从别的语言译出来的轨道，没有中文原字幕再退回英文原字幕；自动字幕去掉滚动重复。B 站按 `FK_BILIBILI_SUB_LANGS` 的顺序挑选。
  - 429：延后重试 2 次，仍失败按“无字幕”处理。
  - 无字幕：新视频自动排 ASR；回填视频标记 `none`，打开条目或点“转写”才排 ASR。
  - ASR（可选，`FK_ASR_PYTHON`）：下载音频，SenseVoiceSmall 在独立 venv 里按 30 秒分段转写（默认 `cuda:0`、batch 2，串行），失败时若配置了 `FK_ASR_CPU_PYTHON` 回退 CPU。

## 索引与检索

- 切块：逐字稿按时间合并，约 1,000–1,500 字、相邻块重叠一句，记录起止时间；文章按 Markdown 小节。向量化文本前加“标题 / 作者”。
- 向量（可选）：Ollama `qwen3-embedding:0.6b`（1024 维，`FK_EMBED_MODEL` 留空则关闭，Ollama 连不上时自动退回关键词），sqlite-vec 余弦距离，平台 / 来源 / 日期作为 vec0 元数据列，可在 KNN 内过滤。
- 关键词：FTS5 trigram；1–2 字查询退回 `LIKE`。
- 检索代码在 `search.py` 一层，规模变大时可换 Qdrant。

## 网站

单页应用：前端在 `frontend/`（Vite + React + TypeScript + Tailwind v4 + shadcn/ui，路由用 react-router，数据用 TanStack Query）；后端 FastAPI 只提供 `/api/*` JSON、`/thumb/*` 缩略图和 `/mcp`，其余路径返回 `frontend/dist/index.html`。前端改动后需要重新 `npm run build`，后端直接读 `dist`，不用重启。

- 首页仿 substack.com：左 Logo、右操作的顶栏；可横向滚动的胶囊筛选（全部 / 未看 / 稍后看 / 视频 / 文章 / 各来源）；四列瀑布流卡片（浅灰大圆角，带缩略图的视频卡跨两列，已看卡片变淡），按发布时间倒序，“加载更多”追加。
- 来源页（Publication）与归档页（按来源、平台、月份）。
- 条目页：标题、作者、日期；嵌入播放器（YouTube IFrame API 可直接跳转；B 站外链播放器带 `t=` 重载）；正文为分段逐字稿，时间戳可点；文章显示全文与原文链接。
- “生成总结”按钮：任意 OpenAI 兼容接口（`FK_LLM_*`），中文；一句话副标题、3–5 条要点、分段正文带时间点；结果写入 `summary.md`。
- 搜索页：语义 / 关键词。

权限：公开只读。浏览、归档、搜索不需要登录；其余都要先在“来源”页输入 `ADMIN_KEY`（存 HttpOnly cookie，30 天）：来源管理、手动投递、已看 / 稍后看（访客看不到这两份记录）、语音转写、生成总结。打开条目页自动抓字幕 / 排队转写也只在登录时触发，避免访客占用 GPU。

公网访问：把反向代理或隧道（如 Cloudflare Tunnel）指向 `127.0.0.1:8090` 即可。

## MCP（只读）

- `search(query?, author?, source?, platform?, date_from?, date_to?, mode="semantic"|"keyword", top_k)`
- `list_items(source?, platform?, date_from?, date_to?, limit)`
- `get_item(id, part="summary"|"transcript"|"full", around_chunk?)`

本机用 stdio（`fk mcp`）；网站同时在 `/mcp` 提供 Streamable HTTP，需 `Authorization: Bearer <ADMIN_KEY>`。

## 运行

```sh
uv sync
(cd frontend && npm install && npm run build)
cp .env.example .env          # 填 ADMIN_KEY
.venv/bin/fk serve            # 网站 + 后台任务 + /mcp，默认 0.0.0.0:8090
.venv/bin/fk poll             # 排队轮询所有来源（定时器调用）
.venv/bin/fk status           # 任务队列
.venv/bin/fk rebuild          # 从文件重建索引
```

前端开发：先跑 `fk serve`，再在 `frontend/` 里 `npm run dev`（Vite 把 `/api`、`/thumb` 代理到 8090）。

systemd（用户级）：

```sh
cp deploy/fk-ai-slop*.{service,timer} ~/.config/systemd/user/   # 改成你的仓库路径
systemctl --user daemon-reload
systemctl --user enable --now fk-ai-slop.service fk-ai-slop-poll.timer
```

小红书容器：`docker compose -f deploy/xiaohongshu-mcp/compose.yml up -d`，登录数据在 `~/.local/share/xiaohongshu-mcp/data`（对应 `FK_XHS_COOKIES`）。掉线后用 `curl 127.0.0.1:18060/api/v1/login/qrcode` 取二维码（`data.img` 是 base64 PNG），App 扫码确认。

MCP（stdio）：`{"command": "<repo>/.venv/bin/fk", "args": ["mcp"]}`；
HTTP：`http://<host>:8090/mcp/`，请求头 `Authorization: Bearer <ADMIN_KEY>`。

## 网络与 GPU

- 代理：`FK_PROXY` 用于 YouTube、RSS、文章和大模型接口；`FK_DIRECT_PLATFORMS`（默认 B 站、小红书）里的平台直连。B 站 CDN 经代理下载容易被断开，音频下载失败时重新解析换节点（最多 4 次）。
- `FK_FORCE_IPV4=1`：直连请求和 yt-dlp 绑定 IPv4，适合 IPv6 路由不通的机器。
- 小显存：GPU 转写前卸载 Ollama 里的 embedding 模型并暂停向量化队列；显存不足导致失败时退回 CPU（需配置 `FK_ASR_CPU_PYTHON`）。

## 已知风险

- B 站空间接口可能返回 -352 风控：带 cookie、限速；失败的轮询下次重试。
- YouTube timedtext 限流：大量回填的逐字稿会很慢，这是预期。
- 小红书同一账号只能在一个网页端登录：在别处登录网页版会把容器挤下线（手机 App 不影响），建议用小号。掉线时主页只返回少量不带 ID 的笔记，轮询会报“需要重新扫码登录”。
