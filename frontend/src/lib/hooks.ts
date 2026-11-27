import { useInfiniteQuery, useQuery } from "@tanstack/react-query"

import { api, query, type FeedPage, type Source, type SummaryTask } from "@/lib/api"

export function usePagedFeed<T extends FeedPage = FeedPage>(
  path: string,
  params: Record<string, string | undefined>,
  enabled = true,
) {
  const result = useInfiniteQuery({
    queryKey: [path, params],
    queryFn: ({ pageParam }) => api.get<T>(`${path}${query({ ...params, page_no: pageParam })}`),
    initialPageParam: 1,
    getNextPageParam: (last, pages) => (last.has_more ? pages.length + 1 : undefined),
    enabled,
  })
  return {
    ...result,
    items: (result.data?.pages.flatMap((page) => page.items) ?? []) as T["items"],
    first: result.data?.pages[0] as T | undefined,
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
