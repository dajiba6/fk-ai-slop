import { useEffect, useRef, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Link, useLocation } from "react-router"
import { Check, ChevronDown, Loader2, Sparkles, TriangleAlert, X } from "lucide-react"

import { api, type SummaryTask } from "@/lib/api"
import { ACTIVE, useAdmin, useSummaryTasks } from "@/lib/hooks"
import { playDone } from "@/lib/sound"
import { cn } from "@/lib/utils"

const STATUS_LABEL: Record<SummaryTask["status"], string> = {
  queued: "排队中",
  transcribing: "转写中",
  summarizing: "总结中",
  done: "已完成，点击查看",
  failed: "失败",
}
const STACK_LIMIT = 3

function TaskIcon({ task, className }: { task: SummaryTask; className?: string }) {
  const active = ACTIVE.includes(task.status)
  return (
    <span className={cn("relative block size-9 shrink-0 rounded-full bg-muted ring-2 ring-background", className)}>
      {task.has_thumb ? (
        <img
          src={`/thumb/${task.id}`}
          alt=""
          className={cn("size-full rounded-full object-cover", active && "opacity-50")}
        />
      ) : (
        <Sparkles className="absolute inset-0 m-auto size-4 text-muted-foreground" />
      )}
      {active && <Loader2 className="absolute inset-0 m-auto size-5 animate-spin text-accent-brand" />}
      {task.status === "done" && (
        <span className="absolute -right-0.5 -bottom-0.5 grid size-4 place-items-center rounded-full bg-emerald-500 text-white ring-2 ring-background">
          <Check className="size-2.5" strokeWidth={3} />
        </span>
      )}
      {task.status === "failed" && (
        <span className="absolute -right-0.5 -bottom-0.5 grid size-4 place-items-center rounded-full bg-destructive text-white ring-2 ring-background">
          <X className="size-2.5" strokeWidth={3} />
        </span>
      )}
    </span>
  )
}

function MiniThumb({ task }: { task: SummaryTask }) {
  return (
    <span
      className={cn(
        "block size-7 overflow-hidden rounded-full bg-muted ring-2 ring-background",
        task.status === "done" && "ring-emerald-500",
        task.status === "failed" && "ring-destructive",
      )}
    >
      {task.has_thumb && (
        <img
          src={`/thumb/${task.id}`}
          alt=""
          className={cn("size-full object-cover", ACTIVE.includes(task.status) && "opacity-50")}
        />
      )}
    </span>
  )
}

export function SummaryDock() {
  const admin = useAdmin()
  const client = useQueryClient()
  const { pathname } = useLocation()
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)

  const tasks = useSummaryTasks(admin)
  const list = tasks.data ?? []

  const dismiss = useMutation({
    mutationFn: (id: string) => api.delete(`/api/summaries/${id}`),
    onSuccess: () => client.invalidateQueries({ queryKey: ["summaries"] }),
  })

  // The post page chimes for its own summary; the dock covers the ones finishing elsewhere.
  const seen = useRef(new Map<string, string>())
  useEffect(() => {
    for (const task of tasks.data ?? []) {
      const before = seen.current.get(task.id)
      if (before && before !== "done" && task.status === "done") {
        if (pathname !== `/p/${task.id}`) playDone()
        client.invalidateQueries({ queryKey: ["/api/feed"] })
      }
      seen.current.set(task.id, task.status)
    }
  }, [client, tasks.data, pathname])

  useEffect(() => {
    if (!open) return
    const close = (event: PointerEvent) => {
      if (!box.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener("pointerdown", close)
    return () => document.removeEventListener("pointerdown", close)
  }, [open])

  if (!admin) return null
  const running = list.filter((t) => ACTIVE.includes(t.status)).length
  const done = list.filter((t) => t.status === "done").length
  const failed = list.filter((t) => t.status === "failed").length
  const label =
    [running && `${running} 个总结中`, done && `${done} 个已完成`, !running && !done && failed && `${failed} 个失败`]
      .filter(Boolean)
      .join(" · ") || "AI 总结"
  const preview = list.slice(-STACK_LIMIT).reverse()

  return (
    <div
      ref={box}
      className={cn(
        "fixed right-4 bottom-6 z-40 overflow-hidden border bg-background/75 shadow-xl backdrop-blur-md sm:right-6",
        open ? "w-[min(22rem,calc(100vw-2rem))] rounded-2xl" : "rounded-full",
      )}
    >
      {open && (
        <div className="max-h-[60vh] overflow-y-auto p-2 pb-0 animate-in duration-200 fade-in slide-in-from-bottom-2">
          {list.length === 0 && <p className="px-2 py-2 text-sm text-muted-foreground">没有进行中的总结</p>}
          {[...list].reverse().map((task) => {
            const body = (
              <>
                <TaskIcon task={task} className="ring-0" />
                <span className="min-w-0 flex-1">
                  <span className="line-clamp-2 text-sm leading-snug font-medium">{task.title}</span>
                  <span
                    className={cn(
                      "mt-0.5 block truncate text-xs text-muted-foreground",
                      task.status === "done" && "text-emerald-600",
                      task.status === "failed" && "text-destructive",
                    )}
                    title={task.error ?? undefined}
                  >
                    {STATUS_LABEL[task.status]}
                    {task.error && `：${task.error}`}
                  </span>
                </span>
              </>
            )
            return (
              <div key={task.id} className="group flex items-center gap-1 rounded-xl hover:bg-black/5">
                {task.status === "done" || task.status === "failed" ? (
                  <Link
                    to={`/p/${task.id}`}
                    onClick={() => setOpen(false)}
                    className="flex min-w-0 flex-1 items-center gap-3 p-2"
                  >
                    {body}
                  </Link>
                ) : (
                  <div className="flex min-w-0 flex-1 items-center gap-3 p-2">{body}</div>
                )}
                <button
                  onClick={() => dismiss.mutate(task.id)}
                  className="mr-1 rounded-full p-1 text-muted-foreground opacity-60 hover:bg-black/5 hover:text-foreground hover:opacity-100"
                  title="移出列表"
                >
                  <X className="size-3.5" />
                </button>
              </div>
            )
          })}
        </div>
      )}
      <button
        onClick={() => setOpen(!open)}
        title={open ? "收起" : label}
        className={cn(
          "flex items-center text-sm font-semibold",
          open ? "mt-1 h-11 w-full gap-2.5 border-t border-black/5 px-3.5" : "w-11 flex-col gap-2 py-3",
        )}
      >
        {!open && preview.length > 0 && (
          <span className="flex flex-col -space-y-2">
            {preview.map((task) => (
              <MiniThumb key={task.id} task={task} />
            ))}
          </span>
        )}
        {running ? (
          <Loader2 className="size-[18px] shrink-0 animate-spin text-accent-brand" />
        ) : failed && !done ? (
          <TriangleAlert className="size-[18px] shrink-0 text-destructive" />
        ) : (
          <Sparkles className="size-[18px] shrink-0 text-accent-brand" />
        )}
        {open && <span className="truncate">{label}</span>}
        {open && <ChevronDown className="ml-auto size-4 shrink-0 text-muted-foreground" />}
      </button>
    </div>
  )
}
