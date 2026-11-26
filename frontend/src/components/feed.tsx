import { useLayoutEffect, useRef, type ReactNode, type SyntheticEvent } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Link } from "react-router"
import { toast } from "sonner"
import { Check, Loader2, Sparkles, TriangleAlert } from "lucide-react"

import { Avatar } from "@/components/avatar"
import { LoadMore } from "@/components/load-more"
import { Skeleton } from "@/components/ui/skeleton"
import { api, type FeedItem, type SummaryTask } from "@/lib/api"
import { ACTIVE, useAdmin, useSite, useSummaryTasks } from "@/lib/hooks"
import { PLATFORM_LABEL, clock, niceDate } from "@/lib/format"
import { unlockSound } from "@/lib/sound"
import { cn } from "@/lib/utils"

const ROW = 4
const GAP = 12
const COLUMNS = "grid-cols-2 min-[700px]:grid-cols-3 min-[1000px]:grid-cols-4 min-[1300px]:grid-cols-5"

/** Grid cell that spans as many 4px rows as its content needs, giving a masonry layout. */
function MasonryCell({ children }: { children: ReactNode }) {
  const cell = useRef<HTMLDivElement>(null)
  const inner = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    const place = () => {
      if (cell.current && inner.current) {
        const height = inner.current.getBoundingClientRect().height + GAP
        cell.current.style.gridRowEnd = `span ${Math.ceil(height / ROW)}`
      }
    }
    place()
    const observer = new ResizeObserver(place)
    if (inner.current) observer.observe(inner.current)
    return () => observer.disconnect()
  }, [])
  return (
    <div ref={cell} className="self-start">
      <div ref={inner}>{children}</div>
    </div>
  )
}

export function Masonry({ children }: { children: ReactNode }) {
  return (
    <div className={cn("grid gap-x-3", COLUMNS)} style={{ gridAutoRows: `${ROW}px` }}>
      {children}
    </div>
  )
}

function SummarizeButton({ item, status }: { item: FeedItem; status?: SummaryTask["status"] }) {
  const client = useQueryClient()
  const start = useMutation({
    mutationFn: () => api.post(`/api/items/${item.id}/summarize`),
    onSuccess: () => client.invalidateQueries({ queryKey: ["summaries"] }),
    onError: (error) => toast.error(error.message),
  })
  const busy = start.isPending || (status != null && ACTIVE.includes(status))
  const failed = status === "failed" && !start.isPending
  const run = (event: SyntheticEvent) => {
    event.preventDefault()
    event.stopPropagation()
    if (busy) return
    unlockSound()
    start.mutate()
  }
  return (
    <span
      role="button"
      tabIndex={0}
      aria-busy={busy}
      title={busy ? "AI 总结进行中" : failed ? "总结失败，点击重试" : "AI 总结"}
      onClick={run}
      onKeyDown={(event) => (event.key === "Enter" || event.key === " ") && run(event)}
      className={cn(
        "-my-1 -mr-1 grid size-6 flex-none place-items-center rounded-full text-muted-foreground transition hover:bg-black/5 hover:text-accent-brand",
        busy && "cursor-default text-accent-brand hover:bg-transparent",
        failed && "text-destructive",
      )}
    >
      {busy ? (
        <Loader2 className="size-3.5 animate-spin" />
      ) : failed ? (
        <TriangleAlert className="size-3.5" />
      ) : (
        <Sparkles className="size-3.5" />
      )}
    </span>
  )
}

function Card({ item, admin, status }: { item: FeedItem; admin: boolean; status?: SummaryTask["status"] }) {
  const summarizable = item.kind !== "note" || !!item.excerpt
  return (
    <Link
      to={`/p/${item.id}`}
      className={cn(
        "relative flex flex-col overflow-hidden rounded-xl bg-card-soft text-foreground transition hover:bg-[#efefef]",
        item.read && "[&>*:not([data-read-mark])]:opacity-55 hover:[&>*:not([data-read-mark])]:opacity-85",
      )}
    >
      {item.read && (
        <span
          data-read-mark
          aria-label="已看"
          title="已看"
          className="absolute top-2 right-2 z-10 flex size-[18px] items-center justify-center rounded-full bg-foreground text-background shadow-sm"
        >
          <Check className="size-3" strokeWidth={3} />
        </span>
      )}
      {item.has_thumb && (
        <div className="relative aspect-video overflow-hidden bg-[#e8e8e8]">
          <img loading="lazy" src={`/thumb/${item.id}`} alt="" className="size-full object-cover" />
          {item.duration ? (
            <span className="absolute right-1.5 bottom-1.5 rounded bg-black/70 px-1 text-[11px] font-semibold text-white tabular-nums">
              {clock(item.duration)}
            </span>
          ) : null}
        </div>
      )}
      <div className="flex flex-col gap-1 px-3 pt-2.5 pb-2.5">
        <div className={cn("flex items-center gap-1.5 text-xs font-semibold", item.read && !item.has_thumb && "pr-5")}>
          <Avatar name={item.source_name} seed={item.source_id} className="size-4 text-[10px]" />
          <span className="truncate">{item.source_name}</span>
        </div>
        <div className="line-clamp-3 text-sm leading-snug font-bold">{item.title || item.id}</div>
        {item.excerpt && !item.has_thumb && (
          <div className="line-clamp-4 text-[13px] leading-relaxed text-foreground/75">{item.excerpt}</div>
        )}
        <div className="flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
          <span className="truncate">
            {niceDate(item.published, item.date_approx)} · {PLATFORM_LABEL[item.platform] ?? item.platform}
          </span>
          {item.has_summary ? (
            <span className="flex-none rounded bg-black/5 px-1 py-px">有总结</span>
          ) : (
            admin && summarizable && <SummarizeButton item={item} status={status} />
          )}
        </div>
      </div>
    </Link>
  )
}

export function FeedGrid({
  items,
  hasMore,
  loadingMore,
  onMore,
}: {
  items: FeedItem[]
  hasMore: boolean
  loadingMore: boolean
  onMore: () => void
}) {
  const admin = useAdmin()
  const site = useSite()
  const canSummarize = admin && site.data?.features.summary !== false
  const tasks = useSummaryTasks(admin)
  const status = new Map(tasks.data?.map((t) => [t.id, t.status]))
  return (
    <>
      <Masonry>
        {items.map((item) => (
          <MasonryCell key={item.id}>
            <Card item={item} admin={canSummarize} status={status.get(item.id)} />
          </MasonryCell>
        ))}
      </Masonry>
      {hasMore && <LoadMore loading={loadingMore} onMore={onMore} />}
    </>
  )
}

export function FeedSkeleton() {
  return (
    <div className={cn("grid gap-3", COLUMNS)}>
      {Array.from({ length: 10 }, (_, i) => (
        <Skeleton key={i} className={cn("rounded-xl", i % 3 === 0 ? "h-56" : "h-40")} />
      ))}
    </div>
  )
}
