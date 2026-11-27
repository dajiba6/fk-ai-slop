import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Link, useSearchParams } from "react-router"
import { Search } from "lucide-react"

import { LoadMore } from "@/components/load-more"
import { Row } from "@/components/rows"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { api, type HistoryPage } from "@/lib/api"
import { PLATFORM_LABEL, clock, niceDate, viewedAt } from "@/lib/format"
import { usePagedFeed } from "@/lib/hooks"

export function HistoryPage() {
  const [params, setParams] = useSearchParams()
  const q = params.get("q") ?? ""
  const [draft, setDraft] = useState(q)
  const me = useQuery({ queryKey: ["admin-me"], queryFn: () => api.get<{ admin: boolean }>("/api/admin/me") })
  const admin = me.data?.admin === true
  const feed = usePagedFeed<HistoryPage>("/api/history", { q }, admin)

  const submit = () => {
    const next = draft.trim()
    const search = new URLSearchParams(params)
    if (next) search.set("q", next)
    else search.delete("q")
    setParams(search)
  }

  return (
    <main className="mx-auto max-w-[728px] px-5 pt-8 pb-24">
      <h1 className="font-serif text-3xl font-bold">历史记录</h1>
      <p className="mt-2 text-sm text-muted-foreground">最近看过的 1000 条。再打开一次会回到最上面。</p>
      <form
        className="mt-6 flex gap-2"
        onSubmit={(event) => {
          event.preventDefault()
          submit()
        }}
      >
        <Input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="搜索标题、作者、来源或正文"
          aria-label="搜索历史记录"
          className="h-10"
          disabled={me.isSuccess && !admin}
        />
        <Button type="submit" className="h-10" disabled={me.isSuccess && !admin}>
          <Search /> 搜索
        </Button>
      </form>

      {me.isPending || (admin && feed.isPending) ? (
        <div className="space-y-6 pt-6">
          {Array.from({ length: 5 }, (_, i) => <Skeleton key={i} className="h-24" />)}
        </div>
      ) : !admin ? (
        <p className="py-16 text-center text-muted-foreground">
          历史记录只记在登录之后。先到<Link to="/admin" className="text-foreground underline">来源</Link>页输入管理密钥。
        </p>
      ) : feed.isError ? (
        <p className="py-16 text-center text-destructive">{feed.error.message}</p>
      ) : feed.items.length === 0 ? (
        <p className="py-16 text-center text-muted-foreground">
          {q ? "没有符合的历史记录。" : "还没有看过的内容。打开一篇，就会出现在这里。"}
        </p>
      ) : (
        <>
          <p className="pt-4 text-xs text-muted-foreground">{q ? `找到 ${feed.first?.total ?? feed.items.length} 条` : `共 ${feed.first?.total ?? feed.items.length} 条`}</p>
          {feed.items.map((item) => (
            <Row
              key={item.id}
              to={`/p/${item.id}`}
              title={item.title || item.id}
              text={item.excerpt}
              thumb={item.has_thumb ? `/thumb/${item.id}` : undefined}
              meta={[
                item.viewed_at && `看过 ${viewedAt(item.viewed_at)}`,
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
