import { useQuery } from "@tanstack/react-query"
import { useParams } from "react-router"

import { Avatar } from "@/components/avatar"
import { FeedGrid, FeedSkeleton } from "@/components/feed"
import { api, type Source } from "@/lib/api"
import { PLATFORM_LABEL, niceDate } from "@/lib/format"
import { usePagedFeed } from "@/lib/hooks"

export function PublicationPage() {
  const { id = "" } = useParams()
  const source = useQuery({
    queryKey: ["source", id],
    queryFn: () => api.get<Source & { total: number }>(`/api/sources/${id}`),
  })
  const feed = usePagedFeed("/api/feed", { source: id })

  return (
    <main className="mx-auto max-w-[1440px] px-4 pt-6 pb-24 sm:px-6">
      {source.data && (
        <header className="mb-10 flex flex-col items-center gap-3 text-center">
          <Avatar name={source.data.name} seed={source.data.id} className="size-16 text-2xl" />
          <h1 className="text-3xl font-bold tracking-tight">{source.data.name}</h1>
          <p className="text-sm text-muted-foreground">
            {PLATFORM_LABEL[source.data.platform] ?? source.data.platform} · {source.data.total} 篇
            {source.data.removed && " · 已停止订阅"}
            {source.data.last_polled && ` · 上次抓取 ${niceDate(source.data.last_polled)}`}
          </p>
          {source.data.url && (
            <a href={source.data.url} target="_blank" rel="noopener" className="text-sm underline underline-offset-4">
              原站
            </a>
          )}
        </header>
      )}
      {source.isError && <p className="py-16 text-center text-muted-foreground">{source.error.message}</p>}
      {feed.isPending ? (
        <FeedSkeleton />
      ) : (
        <FeedGrid
          items={feed.items}
          hasMore={feed.hasNextPage}
          loadingMore={feed.isFetchingNextPage}
          onMore={() => feed.fetchNextPage()}
        />
      )}
    </main>
  )
}
