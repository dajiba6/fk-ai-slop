import { useInfiniteQuery, useQuery } from "@tanstack/react-query"

import { api, query, type FeedPage, type Source, type SummaryTask } from "@/lib/api"

export function usePagedFeed(path: string, params: Record<string, string | undefined>) {
  const result = useInfiniteQuery({
    queryKey: [path, params],
    queryFn: ({ pageParam }) => api.get<FeedPage>(`${path}${query({ ...params, page_no: pageParam })}`),
    initialPageParam: 1,
    getNextPageParam: (last, pages) => (last.has_more ? pages.length + 1 : undefined),
  })
  return {
    ...result,
    items: result.data?.pages.flatMap((page) => page.items) ?? [],
    first: result.data?.pages[0],
  }
}

export function useAdmin() {
  const me = useQuery({ queryKey: ["admin-me"], queryFn: () => api.get<{ admin: boolean }>("/api/admin/me") })
  return me.data?.admin ?? false
}

export function useSources() {
  return useQuery({ queryKey: ["sources"], queryFn: () => api.get<Source[]>("/api/sources") })
}

export const ACTIVE = ["queued", "transcribing", "summarizing"]

export function useSummaryTasks(admin: boolean) {
  return useQuery({
    queryKey: ["summaries"],
    queryFn: () => api.get<SummaryTask[]>("/api/summaries"),
    enabled: admin,
    refetchInterval: (q) => (q.state.data?.some((t) => ACTIVE.includes(t.status)) ? 4000 : 30000),
  })
}

export type Site = { name: string; features: { summary: boolean; asr: boolean } }

export function useSite() {
  return useQuery({ queryKey: ["site"], queryFn: () => api.get<Site>("/api/site"), staleTime: Infinity })
}
