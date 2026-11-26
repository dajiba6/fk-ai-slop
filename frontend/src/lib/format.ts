export const PLATFORM_LABEL: Record<string, string> = {
  youtube: "YouTube",
  bilibili: "B 站",
  xiaohongshu: "小红书",
  article: "文章",
  rss: "RSS",
  podcast: "播客",
  manual: "手动",
}

export const TRANSCRIPT_LABEL: Record<string, string> = {
  pending: "等待抓取字幕",
  asr_queued: "排队语音转写",
  asr_running: "正在语音转写",
  none: "没有字幕",
  failed: "转写失败",
  "n/a": "还没有逐字稿",
}

export function clock(seconds: number | null | undefined) {
  if (seconds == null) return ""
  const total = Math.floor(seconds)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = String(total % 60).padStart(2, "0")
  return h ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`
}

export function niceDate(value: string | null | undefined, approx?: boolean) {
  if (!value) return ""
  const moment = new Date(value)
  if (Number.isNaN(moment.getTime())) return value.slice(0, 10)
  const [y, m, d] = [moment.getFullYear(), moment.getMonth() + 1, moment.getDate()]
  if (approx) return `约 ${y} 年 ${m} 月`
  if (y === new Date().getFullYear()) return `${m} 月 ${d} 日`
  return `${y} 年 ${m} 月 ${d} 日`
}

export function hue(key: string) {
  let hash = 0
  for (const char of key) hash = (hash * 31 + char.charCodeAt(0)) >>> 0
  return hash % 360
}
