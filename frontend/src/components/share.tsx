import { useEffect, useRef, useState, type ComponentProps } from "react"
import { createPortal } from "react-dom"
import Markdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { domToBlob } from "modern-screenshot"
import { toast } from "sonner"
import { Loader2, Share2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import type { ItemDetail } from "@/lib/api"
import { PLATFORM_LABEL, clock, niceDate } from "@/lib/format"

const WIDTH = 750
// Stay under browser canvas limits (Safari caps area at ~16.7M px, Chrome caps a side at 32767 px).
const MAX_AREA = 16_000_000
const MAX_SIDE = 32_000

function PlainLink({ href, children }: ComponentProps<"a">) {
  if (href?.startsWith("#t=")) {
    return <span className="font-sans text-[0.8em] font-semibold text-muted-foreground tabular-nums">{children}</span>
  }
  return <span className="underline underline-offset-3">{children}</span>
}

function loads(src: string) {
  return new Promise<boolean>((resolve) => {
    const img = new Image()
    img.onload = () => resolve(img.naturalWidth > 0)
    img.onerror = () => resolve(false)
    img.src = src
  })
}

function ShareCard({ detail, cover, name }: { detail: ItemDetail; cover: boolean; name: string }) {
  const { item, summary, paragraphs } = detail
  return (
    <div style={{ width: WIDTH }} className="bg-background px-12 pt-12 pb-10 text-foreground">
      {cover && <img src={`/thumb/${item.id}`} alt="" className="mb-8 w-full rounded-xl" />}
      <h1 className="font-serif text-[34px] leading-tight font-bold tracking-tight">{item.title}</h1>
      {item.subtitle && <p className="mt-3 font-serif text-xl leading-snug text-foreground/70">{item.subtitle}</p>}
      <div className="mt-4 text-sm text-muted-foreground">
        {[name, niceDate(item.published, item.date_approx), clock(item.duration), PLATFORM_LABEL[item.platform]]
          .filter(Boolean)
          .join(" · ")}
      </div>

      {summary && (
        <section className="prose-reading mt-8 rounded-xl bg-card-soft px-6 py-5 text-[17px]">
          <div className="mb-2 font-sans text-xs font-bold tracking-widest text-accent-brand uppercase">AI 总结</div>
          <Markdown remarkPlugins={[remarkGfm]} components={{ a: PlainLink }}>{summary}</Markdown>
        </section>
      )}

      {paragraphs.length > 0 && (
        <section className="prose-reading mt-10 text-[17px]">
          <h2 className="!mt-0 font-sans">逐字稿</h2>
          {paragraphs.map((p) => (
            <div key={p.start}>
              {p.heading && <h3>{p.heading}</h3>}
              <p>
                <span className="mr-2 font-sans text-[13px] font-semibold text-muted-foreground tabular-nums">
                  {clock(p.start)}
                </span>
                {p.text}
              </p>
            </div>
          ))}
        </section>
      )}

      <footer className="mt-10 border-t pt-4 text-xs break-all text-muted-foreground">{item.url}</footer>
    </div>
  )
}

async function deliver(blob: Blob, title: string) {
  const file = new File([blob], `${title.replace(/[\\/:*?"<>|\s]+/g, "_").slice(0, 60) || "share"}.png`, {
    type: "image/png",
  })
  if (matchMedia("(pointer: coarse)").matches && navigator.canShare?.({ files: [file] })) {
    try {
      await navigator.share({ files: [file], title })
    } catch (error) {
      if ((error as Error).name !== "AbortError") throw error
    }
    return
  }
  const url = URL.createObjectURL(file)
  const link = document.createElement("a")
  link.href = url
  link.download = file.name
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function ShareButton({ detail, name }: { detail: ItemDetail; name: string }) {
  const [card, setCard] = useState<{ cover: boolean } | null>(null)
  const node = useRef<HTMLDivElement>(null)

  const start = async () => {
    setCard({ cover: await loads(`/thumb/${detail.item.id}`) })
  }

  useEffect(() => {
    if (!card) return
    let cancelled = false
    ;(async () => {
      try {
        await document.fonts.ready
        const target = node.current?.firstElementChild as HTMLElement | null
        if (!target) return
        const w = target.offsetWidth
        const h = target.offsetHeight
        const scale = Math.max(0.5, Math.min(2, MAX_SIDE / h, Math.sqrt(MAX_AREA / (w * h))))
        const blob = await domToBlob(target, { scale, type: "image/png", backgroundColor: "#ffffff" })
        if (!cancelled) await deliver(blob, detail.item.title)
      } catch (error) {
        toast.error(`生成分享图失败：${(error as Error).message}`)
      } finally {
        if (!cancelled) setCard(null)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [card, detail.item.title])

  return (
    <>
      <Button size="sm" variant="outline" className="rounded-full" disabled={!!card} onClick={start}>
        {card ? <Loader2 className="animate-spin" /> : <Share2 />} 分享图片
      </Button>
      {card &&
        createPortal(
          <div ref={node} aria-hidden style={{ position: "fixed", top: 0, left: -100000, pointerEvents: "none" }}>
            <ShareCard detail={detail} cover={card.cover} name={name} />
          </div>,
          document.body,
        )}
    </>
  )
}
