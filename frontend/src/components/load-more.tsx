import { useEffect, useRef } from "react"

import { Button } from "@/components/ui/button"

/** Loads the next page when scrolled near; the button stays as a fallback. */
export function LoadMore({ loading, onMore }: { loading: boolean; onMore: () => void }) {
  const box = useRef<HTMLDivElement>(null)
  const latest = useRef({ loading, onMore })
  useEffect(() => {
    latest.current = { loading, onMore }
  })

  useEffect(() => {
    const node = box.current
    if (!node) return
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !latest.current.loading) latest.current.onMore()
      },
      { rootMargin: "0px 0px 600px 0px" },
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  // A page that does not fill the screen keeps the box in view, which the observer reports only once.
  // Continue only while pages add content, so a failing request does not loop.
  const lastTop = useRef<number | null>(null)
  useEffect(() => {
    const node = box.current
    if (loading || !node) return
    const top = node.getBoundingClientRect().top + window.scrollY
    const grew = lastTop.current === null || top > lastTop.current
    lastTop.current = top
    if (grew && top - window.scrollY < window.innerHeight + 600) latest.current.onMore()
  }, [loading])

  return (
    <div ref={box} className="py-6 text-center">
      <Button variant="secondary" disabled={loading} onClick={onMore}>
        {loading ? "加载中…" : "加载更多"}
      </Button>
    </div>
  )
}
