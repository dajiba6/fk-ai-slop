import type { ReactNode } from "react"
import { Link } from "react-router"

/** Substack archive-style row: text on the left, small thumbnail on the right. */
export function Row({
  to,
  title,
  text,
  meta,
  thumb,
  dim,
}: {
  to: string
  title: string
  text?: ReactNode
  meta: ReactNode
  thumb?: string
  dim?: boolean
}) {
  return (
    <Link to={to} className={`flex gap-6 border-b py-6 ${dim ? "opacity-60 hover:opacity-90" : ""}`}>
      <div className="min-w-0 flex-1">
        <div className="text-lg leading-snug font-bold">{title}</div>
        {text && <div className="mt-1.5 line-clamp-3 text-[15px] leading-relaxed text-foreground/70">{text}</div>}
        <div className="mt-2 text-xs tracking-wide text-muted-foreground">{meta}</div>
      </div>
      {thumb && (
        <img loading="lazy" src={thumb} alt="" className="aspect-video w-28 flex-none self-start rounded-md object-cover sm:w-40" />
      )}
    </Link>
  )
}
