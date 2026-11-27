import { StrictMode } from "react"
import { createRoot } from "react-dom/client"

import "./index.css"
import App from "./App"

let scrollIdle = 0
function revealScrollbar() {
  document.documentElement.classList.add("scrolling")
  clearTimeout(scrollIdle)
  scrollIdle = window.setTimeout(() => document.documentElement.classList.remove("scrolling"), 900)
}
window.addEventListener("scroll", revealScrollbar, { passive: true })
window.addEventListener(
  "mousemove",
  (event) => {
    if (event.clientX >= document.documentElement.clientWidth - 8) revealScrollbar()
  },
  { passive: true },
)

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
