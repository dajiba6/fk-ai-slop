import { useEffect, useRef, useState, type ComponentProps } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useParams } from "react-router"
import Markdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { toast } from "sonner"
import { Check, ExternalLink, ListTodo, Pin, PinOff, Sparkles, Star } from "lucide-react"

import { Avatar } from "@/components/avatar"
import { Player, type PlayerHandle } from "@/components/player"
import { ShareButton } from "@/components/share"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { api, type ItemDetail, type ItemStatus } from "@/lib/api"
import { useAdmin, useSite } from "@/lib/hooks"
import { PLATFORM_LABEL, TRANSCRIPT_LABEL, clock, niceDate } from "@/lib/format"
import { playDone, unlockSound } from "@/lib/sound"
import { cn } from "@/lib/utils"

const WORKING = ["pending", "asr_queued", "asr_running"]
const JOB_ACTIVE = ["queued", "running"]

function snapshot(status: ItemStatus) {
  return JSON.stringify([status.transcript, status.body_status, status.summary, status.summary_job])
}

function detailSnapshot(detail: ItemDetail) {
  return snapshot({
    transcript: detail.item.transcript ?? null,
    body_status: detail.item.body_status ?? null,
    summary: detail.summary != null,
    summary_job: detail.summary_job?.status ?? null,
  })
}

/** Poll the cheap status endpoint while background work runs; refetch the item once anything changes. */
function useLiveDetail(id: string) {
  const client = useQueryClient()
  const detail = useQuery({ queryKey: ["item", id], queryFn: () => api.get<ItemDetail>(`/api/items/${id}`) })
  const data = detail.data
  const busy =
    !!data &&
    (WORKING.includes(data.item.transcript ?? "") ||
      data.item.body_status === "pending" ||
      JOB_ACTIVE.includes(data.summary_job?.status ?? ""))
  const status = useQuery({
    queryKey: ["item-status", id],
    queryFn: () => api.get<ItemStatus>(`/api/items/${id}/status`),
    enabled: busy,
    refetchInterval: 5000,
  })
  useEffect(() => {
    if (data && status.data && snapshot(status.data) !== detailSnapshot(data)) {
      client.invalidateQueries({ queryKey: ["item", id] })
    }
  }, [client, data, id, status.data])
  return detail
}

function seekLink(onSeek: ((seconds: number) => void) | null) {
  return function MarkdownLink({ href, children, ...rest }: ComponentProps<"a">) {
    const match = href?.match(/^#t=(\d+)/)
    if (match && !onSeek) {
      return <span className="font-sans text-[0.8em] font-semibold text-muted-foreground tabular-nums">{children}</span>
    }
    if (match && onSeek) {
      return (
        <a
          href={href}
          onClick={(event) => {
            event.preventDefault()
            onSeek(Number(match[1]))
          }}
          className="font-sans text-[0.8em] font-semibold text-accent-brand no-underline tabular-nums"
        >
          {children}
        </a>
      )
    }
    return (
      <a href={href} target="_blank" rel="noopener" {...rest}>
        {children}
      </a>
    )
  }
}

export function PostPage() {
  const { id = "" } = useParams()
  const client = useQueryClient()
  const detail = useLiveDetail(id)
  const admin = useAdmin()
  const features = useSite().data?.features
  const player = useRef<PlayerHandle>(null)
  const playerBox = useRef<HTMLDivElement>(null)
  const [pinned, setPinned] = useState(false)
  const [initialSeek] = useState(() => {
    const match = location.hash.match(/^#t=(\d+)/)
    return match ? Number(match[1]) : undefined
  })

  const refresh = () => client.invalidateQueries({ queryKey: ["item", id] })

  const flag = useMutation({
    mutationFn: ({ name, on }: { name: "read" | "later" | "favorite"; on: boolean }) =>
      api.post(`/api/items/${id}/flags/${name}`, { on }),
    onSuccess: (_, { name, on }) => {
      client.setQueryData<ItemDetail>(["item", id], (old) => (old ? { ...old, [name]: on } : old))
      client.invalidateQueries({ queryKey: ["/api/feed"] })
    },
    onError: (error) => toast.error(error.message),
  })
  const action = useMutation({
    mutationFn: (name: "summarize" | "transcribe") => api.post(`/api/items/${id}/${name}`),
    onSuccess: () => {
      refresh()
      client.invalidateQueries({ queryKey: ["summaries"] })
    },
    onError: (error) => toast.error(error.message),
  })

  // Opening a post counts as read.
  const autoRead = useRef<string | null>(null)
  const loaded = detail.data
  useEffect(() => {
    if (!admin || !loaded || autoRead.current === id) return
    autoRead.current = id
    if (!loaded.read) flag.mutate({ name: "read", on: true })
  }, [admin, flag, id, loaded])

  const awaitingSummary = useRef<string | null>(null)
  const summaryReady = loaded?.summary != null
  const summaryFailed = loaded?.summary_job?.status === "failed"
  useEffect(() => {
    if (awaitingSummary.current !== id) return
    if (summaryReady) playDone()
    if (summaryReady || summaryFailed) awaitingSummary.current = null
  }, [id, summaryReady, summaryFailed])
  useEffect(() => {
    if (summaryReady || summaryFailed) client.invalidateQueries({ queryKey: ["summaries"] })
  }, [client, summaryReady, summaryFailed])
  const requestSummary = () => {
    unlockSound()
    awaitingSummary.current = id
    action.mutate("summarize")
  }

  const seek = (seconds: number) => {
    player.current?.seek(seconds)
    const box = playerBox.current
    if (box && !pinned) {
      const rect = box.getBoundingClientRect()
      if (rect.bottom < 0 || rect.top > window.innerHeight) box.scrollIntoView({ behavior: "smooth" })
    }
  }

  if (detail.isPending) {
    return (
      <main className="mx-auto max-w-[728px] space-y-4 px-5 pt-10">
        <Skeleton className="h-10 w-4/5" />
        <Skeleton className="h-6 w-2/3" />
        <Skeleton className="aspect-video w-full" />
      </main>
    )
  }
  if (detail.isError) {
    return <p className="py-24 text-center text-muted-foreground">{detail.error.message}</p>
  }

  const { item, source, body, paragraphs, summary, summary_job: summaryJob, read, later, favorite } = detail.data
  const name = source?.name || item.author || "手动投递"
  const summarizing = JOB_ACTIVE.includes(summaryJob?.status ?? "") || action.isPending
  const linkOnly = item.platform === "xiaohongshu"
  const components = { a: seekLink(linkOnly ? null : seek) }

  const transcript = (
    <section className="prose-reading">
      <h2 className="!mt-0 flex items-center gap-2 font-sans">
        逐字稿
        {item.transcript_method === "asr" && (
          <span className="rounded bg-black/5 px-1.5 py-px text-xs font-medium">本地语音识别</span>
        )}
      </h2>
      {paragraphs.length ? (
        paragraphs.map((p) => (
          <div key={p.start}>
            {p.heading && <h3>{p.heading}</h3>}
            <p>
              {linkOnly ? (
                <span className="mr-2 font-sans text-[13px] font-semibold text-muted-foreground tabular-nums">
                  {clock(p.start)}
                </span>
              ) : (
                <a
                  href={`#t=${Math.floor(p.start)}`}
                  onClick={(event) => {
                    event.preventDefault()
                    seek(Math.floor(p.start))
                  }}
                  className="mr-2 font-sans text-[13px] font-semibold text-accent-brand no-underline tabular-nums"
                >
                  {clock(p.start)}
                </a>
              )}
              {p.text}
            </p>
          </div>
        ))
      ) : (
        <p className="font-sans text-base text-muted-foreground">
          {TRANSCRIPT_LABEL[item.transcript ?? ""] ?? item.transcript}
          {item.transcript_note && `（${item.transcript_note}）`}
          {admin && WORKING.includes(item.transcript ?? "") && "，完成后页面会自动更新。"}
          {admin && features?.asr !== false && ["none", "failed", "n/a"].includes(item.transcript ?? "") && (
            <Button
              size="sm"
              variant="outline"
              className="ml-3 rounded-full"
              disabled={action.isPending}
              onClick={() => action.mutate("transcribe")}
            >
              {linkOnly ? "提取逐字稿" : "语音转写"}
            </Button>
          )}
        </p>
      )}
    </section>
  )

  return (
    <main className="mx-auto max-w-[728px] px-5 pt-8 pb-28">
      <title>{item.title}</title>
      <header className="mb-8">
        <h1 className="font-serif text-[32px] leading-tight font-bold tracking-tight sm:text-[40px]">{item.title}</h1>
        {item.subtitle && <p className="mt-3 font-serif text-xl leading-snug text-foreground/70">{item.subtitle}</p>}
        <div className="mt-6 flex items-center gap-3">
          <Link to={`/s/${item.source_id}`}>
            <Avatar name={name} seed={item.source_id} className="size-10 text-base" />
          </Link>
          <div className="text-sm">
            <Link to={`/s/${item.source_id}`} className="font-semibold hover:underline">
              {name}
            </Link>
            <div className="text-muted-foreground">
              {[niceDate(item.published, item.date_approx), clock(item.duration), PLATFORM_LABEL[item.platform]]
                .filter(Boolean)
                .join(" · ")}
            </div>
          </div>
        </div>
        <div className="mt-5 flex flex-wrap gap-2">
          {admin && (
            <>
              <Button
                size="sm"
                variant={read ? "default" : "outline"}
                className="rounded-full"
                onClick={() => flag.mutate({ name: "read", on: !read })}
              >
                <Check /> {read ? "已看" : "标记已看"}
              </Button>
              <Button
                size="sm"
                variant={later ? "default" : "outline"}
                className="rounded-full"
                onClick={() => flag.mutate({ name: "later", on: !later })}
              >
                <ListTodo /> {later ? "已加入稍后看" : "稍后看"}
              </Button>
              <Button
                size="sm"
                variant={favorite ? "default" : "outline"}
                className="rounded-full"
                onClick={() => flag.mutate({ name: "favorite", on: !favorite })}
              >
                <Star className={cn(favorite && "fill-current")} /> {favorite ? "已收藏" : "收藏"}
              </Button>
              {!summary &&
                features?.summary !== false &&
                (!linkOnly || item.kind === "video" || body.trim() || paragraphs.length > 0) && (
                  <Button
                    size="sm"
                    variant="outline"
                    className={cn("rounded-full", summarizing && "ai-shimmer disabled:opacity-100")}
                    disabled={summarizing}
                    aria-busy={summarizing}
                    onClick={requestSummary}
                  >
                    <Sparkles /> 生成总结
                  </Button>
                )}
            </>
          )}
          <Button size="sm" variant="outline" className="rounded-full" asChild>
            <a href={item.url} target="_blank" rel="noopener">
              <ExternalLink /> 原链接
            </a>
          </Button>
          <ShareButton detail={detail.data} name={name} />
        </div>
      </header>

      {item.kind === "video" && !linkOnly && (
        <div ref={playerBox} className={cn("mb-8 scroll-mt-20 bg-background", pinned && "sticky top-16 z-20 pb-2")}>
          <Player
            ref={player}
            platform={item.platform}
            videoId={item.native_id}
            audioUrl={item.audio_url}
            initialSeek={initialSeek}
          />
          <button
            onClick={() => setPinned(!pinned)}
            className="mt-2 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            title="阅读逐字稿时把播放器固定在顶部"
          >
            {pinned ? <PinOff className="size-3.5" /> : <Pin className="size-3.5" />}
            {pinned ? "取消固定" : "固定播放器"}
          </button>
        </div>
      )}

      {summary ? (
        <section className="prose-reading mb-10 rounded-xl bg-card-soft px-6 py-5 text-[17px]">
          <div className="mb-2 font-sans text-xs font-bold tracking-widest text-accent-brand uppercase">AI 总结</div>
          <Markdown remarkPlugins={[remarkGfm]} components={components}>
            {summary}
          </Markdown>
        </section>
      ) : summaryJob?.status === "failed" ? (
        <p className="mb-8 rounded-lg bg-destructive/10 px-4 py-3 text-sm text-destructive">
          总结生成失败：{summaryJob.error}
        </p>
      ) : null}

      {linkOnly ? (
        <section>
          <a
            href={item.url}
            target="_blank"
            rel="noopener"
            className="relative mx-auto block max-w-sm overflow-hidden rounded-lg bg-[#e8e8e8]"
          >
            <img
              src={`/thumb/${item.id}`}
              alt=""
              className="w-full"
              onError={(event) => (event.currentTarget.style.display = "none")}
            />
            <span className="absolute inset-x-0 bottom-0 flex items-center gap-1.5 bg-gradient-to-t from-black/70 px-4 pt-10 pb-3 text-sm font-semibold text-white">
              <ExternalLink className="size-4" /> 在小红书打开
            </span>
          </a>
          {body.trim() && <p className="mt-6 whitespace-pre-line text-foreground/80">{body}</p>}
          {item.kind === "video" && <div className="mt-10">{transcript}</div>}
        </section>
      ) : item.kind === "article" ? (
        <section className="prose-reading">
          {body.trim() ? (
            <Markdown remarkPlugins={[remarkGfm]} components={components}>
              {body}
            </Markdown>
          ) : (
            <p className="text-muted-foreground">
              {item.body_status === "failed" ? "正文抓取失败，请看原链接。" : "正在抓取正文…"}
            </p>
          )}
        </section>
      ) : (
        <>
          {body.trim() && (
            <section className="prose-reading mb-10">
              <h2 className="!mt-0 font-sans">节目简介</h2>
              <Markdown remarkPlugins={[remarkGfm]} components={components}>
                {body.replace(/\n/g, "  \n")}
              </Markdown>
            </section>
          )}
          {transcript}
        </>
      )}
    </main>
  )
}
