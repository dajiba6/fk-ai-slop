import { useEffect, useRef, useState, type ReactNode } from "react"
import { Link, useSearchParams } from "react-router"
import { Check, ChevronDown, ChevronRight } from "lucide-react"

import { Avatar } from "@/components/avatar"
import { FeedGrid, FeedSkeleton } from "@/components/feed"
import { useAdmin, usePagedFeed, useSources } from "@/lib/hooks"
import { cn } from "@/lib/utils"

const PILL =
  "inline-flex h-10 flex-none items-center gap-1.5 rounded-full border px-[18px] text-sm font-medium whitespace-nowrap hover:border-[#c8c8c8]"
const PILL_ACTIVE = "border-foreground bg-foreground font-semibold text-background hover:border-foreground"

function Pills({
  links,
  extra,
  panel,
}: {
  links: { to: string; label: string; active: boolean }[]
  extra?: ReactNode
  panel?: ReactNode
}) {
  const strip = useRef<HTMLElement>(null)
  const [atEnd, setAtEnd] = useState(true)

  useEffect(() => {
    const el = strip.current
    if (!el) return
    const sync = () => setAtEnd(el.scrollLeft + el.clientWidth >= el.scrollWidth - 4)
    sync()
    el.addEventListener("scroll", sync)
    window.addEventListener("resize", sync)
    el.querySelector("[data-active=true]")?.scrollIntoView({
      inline: "center",
      block: "nearest",
    })
    return () => {
      el.removeEventListener("scroll", sync)
      window.removeEventListener("resize", sync)
    }
  }, [links.length])

  return (
    <div className="relative mt-2 mb-5">
      <nav ref={strip} className="scrollbar-none flex gap-2 overflow-x-auto pr-12">
        {links.map((link) => (
          <Link key={link.to} to={link.to} data-active={link.active} className={cn(PILL, link.active && PILL_ACTIVE)}>
            {link.label}
          </Link>
        ))}
        {extra}
      </nav>
      {!atEnd && (
        <button
          aria-label="更多"
          onClick={() =>
            strip.current?.scrollBy({
              left: strip.current.clientWidth * 0.7,
              behavior: "smooth",
            })
          }
          className="absolute top-0 right-0 flex size-10 items-center justify-center rounded-full border bg-background shadow-[-16px_0_16px_#fff]"
        >
          <ChevronRight className="size-5" />
        </button>
      )}
      {panel}
    </div>
  )
}

export function HomePage() {
  const [params, setParams] = useSearchParams()
  const admin = useAdmin()
  const [picking, setPicking] = useState(false)
  const filterBox = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!picking) return
    const close = (event: PointerEvent) => {
      if (!filterBox.current?.contains(event.target as Node)) setPicking(false)
    }
    document.addEventListener("pointerdown", close)
    return () => document.removeEventListener("pointerdown", close)
  }, [picking])
  const tab = params.get("tab") ?? "all"
  const source = params.get("source") ?? ""
  const kind = params.get("kind") ?? ""
  const selected = source.split(",").filter(Boolean)
  const sources = useSources()
  const feed = usePagedFeed("/api/feed", { tab, source, kind })

  const href = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params)
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value)
      else next.delete(key)
    }
    const text = next.toString()
    return text ? `/?${text}` : "/"
  }
  const links = [
    {
      to: href({ tab: null, kind: null }),
      label: "全部",
      active: tab === "all" && !kind,
    },
    ...(admin
      ? [
          {
            to: href({ tab: "unread", kind: null }),
            label: "未看",
            active: tab === "unread" && !kind,
          },
          {
            to: href({ tab: "later", kind: null }),
            label: "稍后看",
            active: tab === "later" && !kind,
          },
          {
            to: href({ tab: "favorite", kind: null }),
            label: "收藏",
            active: tab === "favorite" && !kind,
          },
        ]
      : []),
    {
      to: href({ tab: null, kind: "video" }),
      label: "视频",
      active: kind === "video",
    },
    {
      to: href({ tab: null, kind: "article" }),
      label: "文章",
      active: kind === "article",
    },
  ]

  const creators = (sources.data ?? []).filter((s) => !s.removed || selected.includes(s.id))
  const setSelected = (ids: string[]) => {
    const next = new URLSearchParams(params)
    if (ids.length) next.set("source", ids.join(","))
    else next.delete("source")
    setParams(next)
  }
  const toggle = (id: string) =>
    setSelected(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id])
  const creatorLabel =
    selected.length === 0
      ? "博主"
      : selected.length === 1
        ? (creators.find((s) => s.id === selected[0])?.name ?? "博主")
        : `博主 · ${selected.length}`

  const panel = picking && (
    <div className="absolute inset-x-0 top-full z-30 mt-2 rounded-2xl border bg-background p-3 shadow-lg sm:right-auto sm:w-[560px]">
      <div className="flex flex-wrap gap-2">
        {creators.map((s) => {
          const on = selected.includes(s.id)
          return (
            <button
              key={s.id}
              onClick={() => toggle(s.id)}
              aria-pressed={on}
              className={cn(
                "inline-flex h-9 items-center gap-2 rounded-full border py-1 pr-3.5 pl-1.5 text-sm hover:border-[#c8c8c8]",
                on && "border-foreground bg-foreground/5 font-semibold hover:border-foreground",
              )}
            >
              <Avatar name={s.name} seed={s.id} className="size-6 text-[11px]" />
              {s.name}
              {on && <Check className="size-4" />}
            </button>
          )
        })}
      </div>
      {selected.length > 0 && (
        <div className="mt-3 flex items-center gap-4 text-sm text-muted-foreground">
          <span>已选 {selected.length} 位</span>
          <button onClick={() => setSelected([])} className="hover:text-foreground">
            清空
          </button>
        </div>
      )}
    </div>
  )

  return (
    <main className="mx-auto max-w-[1440px] px-4 pt-2 pb-24 sm:px-6">
      <div ref={filterBox}>
        <Pills
          links={links}
          panel={panel}
          extra={
            creators.length > 0 && (
              <button
                onClick={() => setPicking(!picking)}
                aria-expanded={picking}
                className={cn(PILL, selected.length > 0 && PILL_ACTIVE)}
              >
                {creatorLabel}
                <ChevronDown className={cn("size-4 transition-transform", picking && "rotate-180")} />
              </button>
            )
          }
        />
      </div>
      {feed.isPending ? (
        <FeedSkeleton />
      ) : feed.isError ? (
        <p className="py-16 text-center text-muted-foreground">{feed.error.message}</p>
      ) : feed.items.length ? (
        <FeedGrid
          items={feed.items}
          hasMore={feed.hasNextPage}
          loadingMore={feed.isFetchingNextPage}
          onMore={() => feed.fetchNextPage()}
        />
      ) : (
        <p className="py-16 text-center text-muted-foreground">
          {tab === "later" ? (
            "还没有标记“稍后看”的内容。"
          ) : tab === "unread" ? (
            "都看完了。"
          ) : tab === "favorite" ? (
            "还没有收藏的内容。"
          ) : selected.length ? (
            "选中的博主还没有内容。"
          ) : (
            <>
              还没有内容。到
              <Link to="/admin" className="underline underline-offset-4">
                来源
              </Link>
              添加频道、UP 主或 RSS。
            </>
          )}
        </p>
      )}
    </main>
  )
}
