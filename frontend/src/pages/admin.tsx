import { useState, type FormEvent, type ReactNode } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useNavigate } from "react-router"
import { toast } from "sonner"
import { LogOut, RefreshCw } from "lucide-react"

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api, type Overview, type Source } from "@/lib/api"
import { PLATFORM_LABEL, niceDate } from "@/lib/format"

const JOB_STATUSES = [
  ["queued", "排队"],
  ["running", "进行中"],
  ["done", "完成"],
  ["failed", "失败"],
]

function Login() {
  const client = useQueryClient()
  const [key, setKey] = useState("")
  const login = useMutation({
    mutationFn: () => api.post("/api/admin/login", { key }),
    onSuccess: () => client.invalidateQueries(),
    onError: (error) => toast.error(error.message),
  })
  return (
    <main className="mx-auto max-w-sm px-5 pt-24">
      <h1 className="font-serif text-2xl font-bold">管理来源</h1>
      <p className="mt-2 text-sm text-muted-foreground">输入 .env 里的 ADMIN_KEY。</p>
      <form
        className="mt-6 flex gap-2"
        onSubmit={(event) => {
          event.preventDefault()
          login.mutate()
        }}
      >
        <Input type="password" autoFocus value={key} onChange={(event) => setKey(event.target.value)} />
        <Button type="submit" disabled={!key || login.isPending}>进入</Button>
      </form>
    </main>
  )
}

function UrlForm({
  label,
  placeholder,
  hint,
  submit,
  children,
}: {
  label: string
  placeholder: string
  hint: ReactNode
  submit: (url: string) => Promise<unknown>
  children?: ReactNode
}) {
  const [url, setUrl] = useState("")
  const [busy, setBusy] = useState(false)
  const onSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    try {
      await submit(url.trim())
      setUrl("")
    } catch (error) {
      toast.error((error as Error).message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <form onSubmit={onSubmit} className="rounded-xl bg-card-soft p-5">
      <div className="font-semibold">{label}</div>
      <div className="mt-1 text-xs text-muted-foreground">{hint}</div>
      <div className="mt-3 flex gap-2">
        <Input className="bg-background" value={url} placeholder={placeholder} onChange={(e) => setUrl(e.target.value)} />
        <Button type="submit" disabled={!url.trim() || busy}>{busy ? "处理中…" : "确定"}</Button>
      </div>
      {children}
    </form>
  )
}

function SinceCell({ source, onDone }: { source: Source & { since?: string | null }; onDone: () => void }) {
  const saved = source.since ?? ""
  const [value, setValue] = useState(saved)
  const save = useMutation({
    mutationFn: () => api.post(`/api/admin/sources/${source.id}/since`, { since: value }),
    onSuccess: () => {
      toast.success(value ? `已改为 ${value} 起，正在补抓` : "已改为不限日期，正在补抓")
      onDone()
    },
    onError: (error) => toast.error(error.message),
  })
  return (
    <div className="flex items-center gap-1.5">
      <Input
        type="date"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        className="h-8 w-36 text-xs"
        title="只抓这天及之后发布的内容；清空表示不限"
      />
      {value !== saved && (
        <Button size="sm" variant="outline" className="h-8" disabled={save.isPending} onClick={() => save.mutate()}>
          保存
        </Button>
      )}
    </div>
  )
}

function SourceActions({ source, onDone }: { source: Source; onDone: () => void }) {
  const run = (verb: "remove" | "restore") =>
    api
      .post(`/api/admin/sources/${source.id}/${verb}`)
      .then(onDone)
      .catch((error: Error) => toast.error(error.message))
  if (source.removed) {
    return <Button size="sm" variant="outline" onClick={() => run("restore")}>恢复</Button>
  }
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button size="sm" variant="ghost" className="text-destructive">移除</Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>移除「{source.name}」？</AlertDialogTitle>
          <AlertDialogDescription>停止抓取新内容。已经保存的条目、逐字稿和索引都会保留，之后可以恢复。</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>取消</AlertDialogCancel>
          <AlertDialogAction onClick={() => run("remove")}>移除</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

function Dashboard() {
  const client = useQueryClient()
  const navigate = useNavigate()
  const overview = useQuery({
    queryKey: ["admin-overview"],
    queryFn: () => api.get<Overview>("/api/admin/overview"),
    refetchInterval: 10000,
  })
  const refresh = () => {
    client.invalidateQueries({ queryKey: ["admin-overview"] })
    client.invalidateQueries({ queryKey: ["sources"] })
  }
  const logout = async () => {
    await api.post("/api/admin/logout")
    client.invalidateQueries()
  }
  const poll = useMutation({
    mutationFn: () => api.post<{ queued: number }>("/api/admin/poll"),
    onSuccess: (data) => {
      toast.success(`已排队轮询 ${data.queued} 个来源`)
      refresh()
    },
    onError: (error) => toast.error(error.message),
  })

  const [since, setSince] = useState(`${new Date().getFullYear()}-01-01`)

  const data = overview.data
  const jobKinds = [...new Set((data?.jobs ?? []).map((j) => j.kind))]
  const jobCount = (kind: string, status: string) =>
    data?.jobs.find((j) => j.kind === kind && j.status === status)?.n ?? 0

  return (
    <main className="mx-auto max-w-[960px] px-5 pt-8 pb-24">
      <div className="flex items-center justify-between">
        <h1 className="font-serif text-3xl font-bold">来源</h1>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" disabled={poll.isPending} onClick={() => poll.mutate()}>
            <RefreshCw /> 立即轮询
          </Button>
          <Button variant="ghost" size="sm" onClick={logout}><LogOut /> 退出</Button>
        </div>
      </div>

      <div className="mt-6 grid gap-4 md:grid-cols-2">
        <UrlForm
          label="添加来源"
          placeholder="频道 / UP 主空间 / 小红书分享链接 / 博客或 RSS 地址"
          hint="YouTube 频道、B 站 UP 主空间、小红书博主（贴他任意一条笔记或主页的分享链接）或 RSS。首次只回填起始日期之后的内容（最多 1000 条），小红书只收主页首屏的笔记链接。"
          submit={async (url) => {
            const source = await api.post<Source>("/api/admin/sources", { url, since })
            toast.success(`已添加「${source.name}」，正在抓取`)
            refresh()
          }}
        >
          <label className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
            只抓这天及之后发布的
            <Input
              type="date"
              value={since}
              onChange={(event) => setSince(event.target.value)}
              className="h-8 w-36 bg-background text-xs"
            />
            {since ? "" : "（不限，回填全部历史）"}
          </label>
        </UrlForm>
        <UrlForm
          label="投递单条链接"
          placeholder="视频、小红书笔记或文章链接"
          hint="单个视频、小红书笔记或文章。频道和主页链接会当作来源添加。"
          submit={async (url) => {
            const result = await api.post<{ item?: string; source?: Source }>("/api/admin/submit", { url })
            if (result.item) {
              toast.success("已收录", { action: { label: "打开", onClick: () => navigate(`/p/${result.item}`) } })
            } else if (result.source) {
              toast.success(`已添加来源「${result.source.name}」`)
            }
            refresh()
          }}
        />
      </div>

      <Table className="mt-8">
        <TableHeader>
          <TableRow>
            <TableHead>名称</TableHead>
            <TableHead>平台</TableHead>
            <TableHead className="text-right">条目</TableHead>
            <TableHead className="text-right">有逐字稿</TableHead>
            <TableHead>起始日期</TableHead>
            <TableHead>上次抓取</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {(data?.sources ?? []).map((source) => (
            <TableRow key={source.id} className={source.removed ? "opacity-50" : undefined}>
              <TableCell className="max-w-64">
                <Link to={`/s/${source.id}`} className="font-medium hover:underline">{source.name}</Link>
                {source.removed && <Badge variant="outline" className="ml-2">已移除</Badge>}
                {source.last_error && (
                  <div className="mt-1 truncate text-xs text-destructive" title={source.last_error}>
                    {source.last_error}
                  </div>
                )}
              </TableCell>
              <TableCell>{PLATFORM_LABEL[source.platform] ?? source.platform}</TableCell>
              <TableCell className="text-right tabular-nums">{source.items}</TableCell>
              <TableCell className="text-right tabular-nums">{source.transcripts}</TableCell>
              <TableCell>
                <SinceCell key={source.since ?? ""} source={source} onDone={refresh} />
              </TableCell>
              <TableCell className="text-muted-foreground">{niceDate(source.last_polled) || "—"}</TableCell>
              <TableCell className="text-right">
                <SourceActions source={source} onDone={refresh} />
              </TableCell>
            </TableRow>
          ))}
          {data && data.sources.length === 0 && (
            <TableRow>
              <TableCell colSpan={7} className="py-8 text-center text-muted-foreground">还没有来源。</TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>

      <h2 className="mt-12 text-lg font-bold">后台任务</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        向量索引 {data?.embedded.done ?? 0} / {data?.embedded.total ?? 0} 段
      </p>
      <Table className="mt-3">
        <TableHeader>
          <TableRow>
            <TableHead>任务</TableHead>
            {JOB_STATUSES.map(([status, label]) => (
              <TableHead key={status} className="w-24 text-right">{label}</TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {jobKinds.map((kind) => (
            <TableRow key={kind}>
              <TableCell>{kind}</TableCell>
              {JOB_STATUSES.map(([status]) => (
                <TableCell key={status} className="text-right tabular-nums">{jobCount(kind, status) || ""}</TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>

      {data && data.failures.length > 0 && (
        <>
          <h2 className="mt-12 text-lg font-bold">最近失败</h2>
          <Table className="mt-3">
            <TableBody>
              {data.failures.map((f, i) => (
                <TableRow key={i}>
                  <TableCell className="w-24">{f.kind}</TableCell>
                  <TableCell className="w-48">
                    <Link to={`/p/${f.target}`} className="hover:underline">{f.target}</Link>
                  </TableCell>
                  <TableCell className="max-w-96 truncate text-xs text-muted-foreground" title={f.error}>
                    {f.error}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </>
      )}
    </main>
  )
}

export function AdminPage() {
  const me = useQuery({ queryKey: ["admin-me"], queryFn: () => api.get<{ admin: boolean }>("/api/admin/me") })
  if (me.isPending) return null
  return me.data?.admin ? <Dashboard /> : <Login />
}
