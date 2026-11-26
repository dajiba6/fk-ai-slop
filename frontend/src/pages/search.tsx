import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { useSearchParams } from "react-router"
import { Search } from "lucide-react"

import { Row } from "@/components/rows"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { api, query, type Hit } from "@/lib/api"
import { PLATFORM_LABEL, clock, niceDate } from "@/lib/format"

export function SearchPage() {
  const [params, setParams] = useSearchParams()
  const q = params.get("q") ?? ""
  const mode = params.get("mode") ?? "semantic"
  const [draft, setDraft] = useState(q)
  const results = useQuery({
    queryKey: ["search", q, mode],
    queryFn: () => api.get<Hit[]>(`/api/search${query({ q, mode })}`),
    enabled: q.trim() !== "",
  })

  const submit = (nextMode = mode) => {
    if (draft.trim()) setParams({ q: draft.trim(), mode: nextMode })
  }

  return (
    <main className="mx-auto max-w-[728px] px-5 pt-8 pb-24">
      <h1 className="font-serif text-3xl font-bold">搜索</h1>
      <form
        className="mt-6 flex gap-2"
        onSubmit={(event) => {
          event.preventDefault()
          submit()
        }}
      >
        <Input
          autoFocus
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="搜逐字稿、文章正文和标题"
          className="h-10"
        />
        <Select value={mode} onValueChange={submit}>
          <SelectTrigger className="h-10 w-28"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="semantic">语义</SelectItem>
            <SelectItem value="keyword">关键词</SelectItem>
          </SelectContent>
        </Select>
        <Button type="submit" className="h-10"><Search /> 搜索</Button>
      </form>

      {results.isFetching && !results.data ? (
        <div className="space-y-6 pt-6">
          {Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-24" />)}
        </div>
      ) : results.isError ? (
        <p className="py-12 text-center text-destructive">{results.error.message}</p>
      ) : results.data?.length === 0 ? (
        <p className="py-12 text-center text-muted-foreground">没有找到相关内容。</p>
      ) : (
        results.data?.map((hit, index) => (
          <Row
            key={`${hit.item_id}-${index}`}
            to={`/p/${hit.item_id}${hit.start != null ? `#t=${Math.floor(hit.start)}` : ""}`}
            title={hit.title}
            text={hit.text}
            meta={[
              niceDate(hit.published),
              hit.author,
              PLATFORM_LABEL[hit.platform],
              hit.start != null && `${clock(hit.start)} 处`,
              hit.section,
            ]
              .filter(Boolean)
              .join(" · ")}
          />
        ))
      )}
    </main>
  )
}
