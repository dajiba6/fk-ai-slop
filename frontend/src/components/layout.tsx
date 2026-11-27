import { useQuery } from "@tanstack/react-query"
import { Link, NavLink, Outlet, ScrollRestoration } from "react-router"

import { SummaryDock } from "@/components/summary-dock"
import { Toaster } from "@/components/ui/sonner"
import { api } from "@/lib/api"
import { useSite } from "@/lib/hooks"
import { cn } from "@/lib/utils"

function TopBar() {
  const site = useSite()
  const me = useQuery({ queryKey: ["admin-me"], queryFn: () => api.get<{ admin: boolean }>("/api/admin/me") })
  const siteName = site.data?.name ?? ""
  const admin = me.data?.admin === true
  const navClass = ({ isActive }: { isActive: boolean }) =>
    cn("text-sm font-semibold whitespace-nowrap text-foreground/70 hover:text-foreground", isActive && "text-foreground")
  return (
    <header className="sticky top-0 z-30 bg-background/95 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-[1440px] items-center justify-between gap-3 px-4 sm:px-6">
        <Link to="/" className="flex min-w-0 items-center gap-2">
          <img src="/logo.png" alt="" className="size-7 rounded-md" />
          <span className="truncate font-display text-[16px] font-extrabold tracking-[0.04em] whitespace-nowrap uppercase sm:text-[21px]">
            {siteName}
          </span>
        </Link>
        <nav className="flex shrink-0 items-center gap-3 sm:gap-5">
          <NavLink to="/archive" className={navClass}>
            归档
          </NavLink>
          <NavLink to="/search" className={navClass}>
            搜索
          </NavLink>
          <NavLink to="/history" className={navClass}>
            历史
          </NavLink>
          {admin ? (
            <NavLink to="/admin" className={navClass}>
              来源
            </NavLink>
          ) : (
            <Link
              to="/admin"
              className="inline-flex h-9 items-center rounded-lg bg-accent-brand px-3 text-sm font-semibold whitespace-nowrap text-white sm:px-4 hover:brightness-95"
            >
              来源
            </Link>
          )}
        </nav>
      </div>
    </header>
  )
}

export function Layout() {
  return (
    <>
      <TopBar />
      <Outlet />
      <SummaryDock />
      <Toaster position="bottom-center" />
      <ScrollRestoration />
    </>
  )
}
