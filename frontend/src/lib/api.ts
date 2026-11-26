export type FeedItem = {
  id: string
  kind: "video" | "article" | "note"
  platform: string
  title: string
  author: string
  source_id: string
  source_name: string
  published: string
  date_approx: boolean
  duration: number | null
  excerpt: string
  has_thumb: boolean
  has_summary: boolean
  transcript: string | null
  read: boolean
  later: boolean
  favorite: boolean
}

export type FeedPage = { items: FeedItem[]; has_more: boolean }

export type Source = {
  id: string
  platform: string
  name: string
  url: string
  removed?: boolean
  last_polled?: string
  last_error?: string
}

export type Paragraph = { start: number; text: string; heading: string | null }

export type ItemDetail = {
  item: {
    id: string
    kind: "video" | "article" | "note"
    platform: string
    native_id: string
    title: string
    subtitle?: string
    author?: string
    url: string
    published: string
    date_approx?: boolean
    duration?: number
    transcript?: string
    transcript_method?: string
    transcript_note?: string
    body_status?: string
    source_id: string
    audio_url?: string | null
  }
  source: Source | null
  body: string
  paragraphs: Paragraph[]
  summary: string | null
  summary_job: { status: string; error: string | null } | null
  read: boolean
  later: boolean
  favorite: boolean
}

export type ItemStatus = {
  transcript: string | null
  body_status: string | null
  summary: boolean
  summary_job: string | null
}

export type Hit = {
  item_id: string
  title: string
  author: string
  platform: string
  source_id: string
  published: string
  start: number | null
  section: string | null
  text: string | null
  score: number
  url: string
}

export type Overview = {
  sources: (Source & { items: number; transcripts: number; since: string | null })[]
  jobs: { kind: string; status: string; n: number }[]
  failures: { kind: string; target: string; error: string; updated_at: number }[]
  embedded: { done: number; total: number }
}

export type SummaryTask = {
  id: string
  title: string
  has_thumb: boolean
  status: "queued" | "transcribing" | "summarizing" | "done" | "failed"
  error: string | null
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
  })
  const data = await response.json().catch(() => null)
  if (!response.ok) throw new ApiError(response.status, data?.detail ?? `请求失败（${response.status}）`)
  return data as T
}

export function query(params: Record<string, string | number | undefined>) {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ""
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
}
