import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { createBrowserRouter, RouterProvider } from "react-router"

import { Layout } from "@/components/layout"
import { TooltipProvider } from "@/components/ui/tooltip"
import { AdminPage } from "@/pages/admin"
import { ArchivePage } from "@/pages/archive"
import { HistoryPage } from "@/pages/history"
import { HomePage } from "@/pages/home"
import { PostPage } from "@/pages/post"
import { PublicationPage } from "@/pages/publication"
import { SearchPage } from "@/pages/search"

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false } },
})

const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: "/", element: <HomePage /> },
      { path: "/p/:id", element: <PostPage /> },
      { path: "/s/:id", element: <PublicationPage /> },
      { path: "/archive", element: <ArchivePage /> },
      { path: "/history", element: <HistoryPage /> },
      { path: "/search", element: <SearchPage /> },
      { path: "/admin", element: <AdminPage /> },
      { path: "*", element: <p className="py-24 text-center text-muted-foreground">页面不存在。</p> },
    ],
  },
])

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <RouterProvider router={router} />
      </TooltipProvider>
    </QueryClientProvider>
  )
}
