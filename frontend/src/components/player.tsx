import { useEffect, useImperativeHandle, useRef, useState, type Ref } from "react"

export type PlayerHandle = { seek: (seconds: number) => void }

type YTPlayer = { seekTo: (s: number, allowSeekAhead: boolean) => void; playVideo: () => void; destroy: () => void }

declare global {
  interface Window {
    YT?: { Player: new (el: HTMLElement, options: object) => YTPlayer }
    onYouTubeIframeAPIReady?: () => void
  }
}

let youtubeApi: Promise<void> | null = null

function loadYoutubeApi() {
  youtubeApi ??= new Promise((resolve) => {
    if (window.YT?.Player) return resolve()
    window.onYouTubeIframeAPIReady = () => resolve()
    const tag = document.createElement("script")
    tag.src = "https://www.youtube.com/iframe_api"
    document.head.appendChild(tag)
  })
  return youtubeApi
}

function bilibiliSrc(bvid: string, start?: number) {
  const base = `https://player.bilibili.com/player.html?bvid=${bvid}&page=1&high_quality=1&danmaku=0`
  return start == null ? `${base}&autoplay=0` : `${base}&autoplay=1&t=${start}`
}

function AudioPlayer({ src, initialSeek, ref }: { src: string; initialSeek?: number; ref: Ref<PlayerHandle> }) {
  const audio = useRef<HTMLAudioElement>(null)

  useImperativeHandle(ref, () => ({
    seek(seconds) {
      const element = audio.current
      if (!element) return
      element.currentTime = seconds
      void element.play()
    },
  }))

  return (
    <audio
      ref={audio}
      src={initialSeek == null ? src : `${src}#t=${initialSeek}`}
      controls
      preload="metadata"
      className="w-full"
    />
  )
}

export function Player({
  platform,
  videoId,
  audioUrl,
  initialSeek,
  ref,
}: {
  platform: string
  videoId: string
  audioUrl?: string | null
  initialSeek?: number
  ref: Ref<PlayerHandle>
}) {
  if (audioUrl) return <AudioPlayer src={audioUrl} initialSeek={initialSeek} ref={ref} />
  return <VideoPlayer platform={platform} videoId={videoId} initialSeek={initialSeek} ref={ref} />
}

function VideoPlayer({
  platform,
  videoId,
  initialSeek,
  ref,
}: {
  platform: string
  videoId: string
  initialSeek?: number
  ref: Ref<PlayerHandle>
}) {
  const holder = useRef<HTMLDivElement>(null)
  const youtube = useRef<YTPlayer | null>(null)
  const pending = useRef<number | undefined>(initialSeek)
  const [bilibili, setBilibili] = useState({ start: initialSeek, count: 0 })

  useEffect(() => {
    if (platform !== "youtube" || !holder.current) return
    let cancelled = false
    const mount = document.createElement("div")
    holder.current.appendChild(mount)
    loadYoutubeApi().then(() => {
      if (cancelled || !window.YT) return
      const player = new window.YT.Player(mount, {
        videoId,
        width: "100%",
        height: "100%",
        playerVars: { rel: 0, modestbranding: 1, playsinline: 1 },
        events: {
          onReady: () => {
            youtube.current = player
            if (pending.current != null) {
              player.seekTo(pending.current, true)
              player.playVideo()
            }
          },
        },
      })
    })
    return () => {
      cancelled = true
      youtube.current?.destroy()
      youtube.current = null
      mount.remove()
    }
  }, [platform, videoId])

  useImperativeHandle(ref, () => ({
    seek(seconds) {
      if (platform === "youtube") {
        if (youtube.current) {
          youtube.current.seekTo(seconds, true)
          youtube.current.playVideo()
        } else {
          pending.current = seconds
        }
      } else {
        setBilibili((previous) => ({ start: seconds, count: previous.count + 1 }))
      }
    },
  }))

  return (
    <div
      ref={holder}
      className="aspect-video w-full overflow-hidden rounded-lg bg-black [&>div]:size-full [&_iframe]:size-full"
    >
      {platform === "bilibili" && (
        <iframe
          key={bilibili.count}
          src={bilibiliSrc(videoId, bilibili.start)}
          allow="fullscreen; autoplay"
          allowFullScreen
          className="size-full border-0"
        />
      )}
    </div>
  )
}
