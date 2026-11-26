import { useQuery } from "@tanstack/react-query"
import { useSearchParams } from "react-router"

import { Row } from "@/components/rows"
import { LoadMore } from "@/components/load-more"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { api, type FeedPage } from "@/lib/api"
import { PLATFORM_LABEL, clock, niceDate } from "@/lib/format"
import { usePagedFeed, useSources } from "@/lib/hooks"

const ALL = "_all"

export function ArchivePage() {
  const [params, setParams] = useSearchParams()
  const filters = {
    source: params.get("source") ?? "",
    platform: params.get("platform") ?? "",
    month: params.get("month") ?? "",
  }
  const sources = useSources()
  const months = useQuery({
    queryKey: ["archive-months"],
    queryFn: () => api.get<FeedPage & { months: string[] }>("/api/archive").then((page) => page.months),
  })
  const feed = usePagedFeed("/api/archive", filters)

  const set = (key: keyof typeof filters, value: string) => {
    const next = new URLSearchParams(params)
    if (value === ALL) next.delete(key)
    else next.set(key, value)
    setParams(next)
  }

  return (
    <main className="mx-auto max-w-[728px] px-5 pt-8 pb-24">
      <h1 className="font-serif text-3xl font-bold">归档</h1>
      <div className="mt-6 flex flex-wrap gap-2 border-b pb-4">
        <Select value={filters.source || ALL} onValueChange={(v) => set("source", v)}>
          <SelectTrigger className="w-44"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>全部来源</SelectItem>
            {(sources.data ?? []).map((s) => (
              <SelectItem key={s.id} value={s.id}>{s.name}{s.removed ? "（已移除）" : ""}</SelectItem>
            ))}
            <SelectItem value="manual">手动投递</SelectItem>
          </SelectContent>
        </Select>
        <Select value={filters.platform || ALL} onValueChange={(v) => set("platform", v)}>
          <SelectTrigger className="w-32"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>全部平台</SelectItem>
            {["youtube", "bilibili", "xiaohongshu", "article"].map((p) => (
              <SelectItem key={p} value={p}>{PLATFORM_LABEL[p]}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={filters.month || ALL} onValueChange={(v) => set("month", v)}>
          <SelectTrigger className="w-32"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>全部时间</SelectItem>
            {(months.data ?? []).map((m) => (
              <SelectItem key={m} value={m}>{m}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {feed.isPending ? (
        <div className="space-y-6 pt-6">
          {Array.from({ length: 5 }, (_, i) => <Skeleton key={i} className="h-24" />)}
        </div>
      ) : feed.items.length === 0 ? (
        <p className="py-16 text-center text-muted-foreground">没有符合条件的内容。</p>
      ) : (
        <>
          {feed.items.map((item) => (
            <Row
              key={item.id}
              to={`/p/${item.id}`}
              title={item.title || item.id}
              text={item.excerpt}
              dim={item.read}
              thumb={item.has_thumb ? `/thumb/${item.id}` : undefined}
              meta={[
                niceDate(item.published, item.date_approx),
                item.source_name,
                PLATFORM_LABEL[item.platform],
                clock(item.duration),
              ]
                .filter(Boolean)
                .join(" · ")}
            />
          ))}
          {feed.hasNextPage && (
            <LoadMore loading={feed.isFetchingNextPage} onMore={() => feed.fetchNextPage()} />
          )}
        </>
      )}
    </main>
  )
}
