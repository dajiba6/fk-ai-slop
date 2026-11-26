import { hue } from "@/lib/format"
import { cn } from "@/lib/utils"

export function Avatar({ name, seed, className }: { name: string; seed: string; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex size-[22px] flex-none items-center justify-center rounded-full text-xs font-bold text-white",
        className,
      )}
      style={{ background: `hsl(${hue(seed)} 45% 42%)` }}
    >
      {(name || "?").slice(0, 1)}
    </span>
  )
}
