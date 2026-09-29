import clsx from "clsx";
import { X } from "lucide-react";
import { type ButtonHTMLAttributes, type ReactNode, useEffect } from "react";
import { createPortal } from "react-dom";

// ----------------------------------------------------------------------------- Button

type Variant = "primary" | "secondary" | "ghost" | "danger" | "success";
const variants: Record<Variant, string> = {
  primary: "bg-ink text-white hover:bg-ink-soft shadow-[0_1px_0_rgb(255_255_255/0.08)_inset,0_1px_2px_rgb(0_0_0/0.2)]",
  secondary: "bg-white text-ink border border-line-strong hover:bg-[#fafbfc] shadow-[var(--shadow-card)]",
  ghost: "text-ink-soft hover:bg-black/[0.04]",
  danger: "bg-white text-rose-700 border border-rose-200 hover:bg-rose-50",
  success: "bg-emerald-700 text-white hover:bg-emerald-800 shadow-[0_1px_2px_rgb(0_0_0/0.15)]",
};

export function Button({
  variant = "secondary", size = "md", icon, loading, className, children, ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md"; icon?: ReactNode; loading?: boolean }) {
  return (
    <button
      {...rest}
      disabled={rest.disabled || loading}
      className={clsx(
        "inline-flex items-center justify-center gap-1.5 rounded-lg font-medium whitespace-nowrap transition-colors disabled:opacity-50 disabled:cursor-not-allowed",
        size === "sm" ? "h-7 px-2.5 text-[12px]" : "h-9 px-3.5 text-[13px]",
        variants[variant],
        className,
      )}
    >
      {loading ? <Spinner className="size-3.5" /> : icon}
      {children}
    </button>
  );
}

// ----------------------------------------------------------------------------- Badge

type Tone = "neutral" | "blue" | "amber" | "green" | "red" | "violet" | "gold";
const tones: Record<Tone, string> = {
  neutral: "bg-[#f1f2f4] text-[#3f4652] ring-[#e3e5e9]",
  blue: "bg-[#eef3ff] text-[#2146b8] ring-[#d9e3ff]",
  amber: "bg-[#fff6e6] text-[#9a5b00] ring-[#fbe3b8]",
  green: "bg-[#ecf8f1] text-[#136c3f] ring-[#cdebd9]",
  red: "bg-[#fdf0f0] text-[#a8242a] ring-[#f6d4d4]",
  violet: "bg-[#f4f1fe] text-[#5534b8] ring-[#e4dcfb]",
  gold: "bg-accent-soft text-[#8a5a0b] ring-[#f1dfb8]",
};

export function Badge({ tone = "neutral", dot, children, className }: { tone?: Tone; dot?: boolean; children: ReactNode; className?: string }) {
  return (
    <span className={clsx("inline-flex items-center gap-1.5 rounded-md px-1.5 py-0.5 text-[11.5px] font-medium ring-1 ring-inset whitespace-nowrap", tones[tone], className)}>
      {dot && <span className="size-1.5 rounded-full bg-current opacity-80" />}
      {children}
    </span>
  );
}

// ----------------------------------------------------------------------------- Card

export function Card({ title, subtitle, actions, children, className, bodyClassName }: {
  title?: ReactNode; subtitle?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; bodyClassName?: string;
}) {
  return (
    <section className={clsx("card overflow-hidden", className)}>
      {(title || actions) && (
        <header className="flex items-start justify-between gap-4 border-b border-line px-5 py-3.5">
          <div>
            {title && <h3 className="text-[13.5px] font-semibold text-ink">{title}</h3>}
            {subtitle && <p className="mt-0.5 text-[12px] text-muted">{subtitle}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={clsx(bodyClassName ?? "p-5")}>{children}</div>
    </section>
  );
}

export function Stat({ label, value, hint, emphasis }: { label: string; value: ReactNode; hint?: ReactNode; emphasis?: boolean }) {
  return (
    <div className={clsx("px-5 py-4", emphasis && "bg-[#fbfbfc]")}>
      <div className="label">{label}</div>
      <div className="mt-1.5 text-[20px] font-semibold tracking-[-0.01em] text-ink tnum">{value}</div>
      {hint && <div className="mt-1 text-[12px] text-muted">{hint}</div>}
    </div>
  );
}

export function StatGrid({ children, cols = 4 }: { children: ReactNode; cols?: number }) {
  return (
    <div className={clsx("card grid divide-x divide-line overflow-hidden", {
      "grid-cols-2 md:grid-cols-4": cols === 4, "grid-cols-2 md:grid-cols-5": cols === 5, "grid-cols-2 md:grid-cols-6": cols === 6, "grid-cols-3": cols === 3,
    })}>{children}</div>
  );
}

// ----------------------------------------------------------------------------- Tabs

export function Tabs<T extends string>({ value, onChange, items }: { value: T; onChange: (v: T) => void; items: { value: T; label: ReactNode; count?: number }[] }) {
  return (
    <div className="flex items-center gap-1 border-b border-line">
      {items.map((it) => (
        <button
          key={it.value}
          onClick={() => onChange(it.value)}
          className={clsx(
            "relative -mb-px inline-flex h-10 items-center gap-2 px-3 text-[13px] font-medium transition-colors",
            value === it.value ? "text-ink after:absolute after:inset-x-2 after:bottom-0 after:h-[2px] after:rounded-full after:bg-ink" : "text-muted hover:text-ink",
          )}
        >
          {it.label}
          {it.count !== undefined && (
            <span className={clsx("rounded-full px-1.5 text-[11px] tnum", value === it.value ? "bg-ink text-white" : "bg-[#eef0f3] text-muted")}>{it.count}</span>
          )}
        </button>
      ))}
    </div>
  );
}

export function Segmented<T extends string>({ value, onChange, items }: { value: T; onChange: (v: T) => void; items: { value: T; label: ReactNode }[] }) {
  return (
    <div className="inline-flex rounded-lg border border-line-strong bg-[#f3f4f6] p-0.5">
      {items.map((it) => (
        <button key={it.value} onClick={() => onChange(it.value)}
          className={clsx("h-7 rounded-md px-2.5 text-[12px] font-medium transition", value === it.value ? "bg-white text-ink shadow-[var(--shadow-card)]" : "text-muted hover:text-ink")}>
          {it.label}
        </button>
      ))}
    </div>
  );
}

// ----------------------------------------------------------------------------- Overlays

function useEscape(onClose: () => void) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);
}

export function Sheet({ open, onClose, title, subtitle, children, footer, width = 720 }: {
  open: boolean; onClose: () => void; title: ReactNode; subtitle?: ReactNode; children: ReactNode; footer?: ReactNode; width?: number;
}) {
  useEscape(onClose);
  if (!open) return null;
  return createPortal(
    <div className="fixed inset-0 z-50">
      <div className="absolute inset-0 bg-[#0b1220]/25 animate-fade-in" onClick={onClose} />
      <aside style={{ width }} className="animate-slide-in absolute inset-y-0 right-0 flex max-w-full flex-col bg-white shadow-[var(--shadow-pop)]">
        <header className="flex items-start justify-between gap-4 border-b border-line px-6 py-4">
          <div className="min-w-0">
            <h2 className="truncate text-[15px] font-semibold text-ink">{title}</h2>
            {subtitle && <div className="mt-0.5 text-[12px] text-muted">{subtitle}</div>}
          </div>
          <button onClick={onClose} className="rounded-md p-1 text-muted hover:bg-black/5 hover:text-ink" aria-label="Close"><X className="size-4" /></button>
        </header>
        <div className="flex-1 overflow-y-auto px-6 py-5">{children}</div>
        {footer && <footer className="border-t border-line bg-[#fafbfc] px-6 py-3">{footer}</footer>}
      </aside>
    </div>,
    document.body,
  );
}

export function Dialog({ open, onClose, title, children, footer }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; footer?: ReactNode }) {
  useEscape(onClose);
  if (!open) return null;
  return createPortal(
    <div className="fixed inset-0 z-50 grid place-items-center p-4">
      <div className="absolute inset-0 bg-[#0b1220]/30 animate-fade-in" onClick={onClose} />
      <div className="animate-fade-in relative w-full max-w-md rounded-xl bg-white shadow-[var(--shadow-pop)]">
        <header className="border-b border-line px-5 py-3.5 text-[14px] font-semibold">{title}</header>
        <div className="px-5 py-4">{children}</div>
        {footer && <footer className="flex justify-end gap-2 border-t border-line bg-[#fafbfc] px-5 py-3 rounded-b-xl">{footer}</footer>}
      </div>
    </div>,
    document.body,
  );
}

// ----------------------------------------------------------------------------- Misc

export function Field({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[12px] font-medium text-ink-soft">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[11.5px] text-muted">{hint}</span>}
    </label>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <svg className={clsx("animate-spin", className ?? "size-4")} viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity=".2" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx("animate-pulse rounded-md bg-[#eceef1]", className)} />;
}

export function Empty({ icon, title, description, action }: { icon?: ReactNode; title: string; description?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-14 text-center">
      {icon && <div className="mb-3 grid size-10 place-items-center rounded-full bg-[#f1f2f4] text-muted">{icon}</div>}
      <div className="text-[14px] font-semibold text-ink">{title}</div>
      {description && <div className="mt-1 max-w-sm text-[12.5px] text-muted">{description}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Meter({ value, tone = "ink" }: { value: number; tone?: "ink" | "green" | "amber" | "red" }) {
  const color = { ink: "bg-ink", green: "bg-emerald-600", amber: "bg-amber-500", red: "bg-rose-600" }[tone];
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-[#eceef1]">
      <div className={clsx("h-full rounded-full", color)} style={{ width: `${Math.max(2, Math.min(100, value * 100))}%` }} />
    </div>
  );
}

export function KeyValue({ items, cols = 2 }: { items: { label: string; value: ReactNode; hint?: ReactNode }[]; cols?: number }) {
  return (
    <dl className={clsx("grid gap-x-6 gap-y-4", cols === 3 ? "grid-cols-3" : cols === 4 ? "grid-cols-2 md:grid-cols-4" : "grid-cols-2")}>
      {items.map((it) => (
        <div key={it.label} className="min-w-0">
          <dt className="label">{it.label}</dt>
          <dd className="mt-1 truncate text-[13px] text-ink">{it.value ?? "—"}</dd>
          {it.hint && <dd className="mt-0.5 text-[11.5px] text-muted">{it.hint}</dd>}
        </div>
      ))}
    </dl>
  );
}
