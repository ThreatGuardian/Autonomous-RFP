import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { BarChart3, Boxes, FileStack, Globe, Landmark, LayoutDashboard, LogOut, Plus, Radar, Settings2 } from "lucide-react";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { api } from "../../lib/api";
import { initials, useAuth } from "../../lib/auth";

export function Logo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className}>
      <rect width="32" height="32" rx="7" fill="#0B1220" />
      <path d="M9 10h14v3h-5.5v11h-3V13H9z" fill="#fff" />
      <rect x="19.5" y="19" width="4" height="4" rx="1" fill="#E0A43A" />
    </svg>
  );
}

function NavItem({ to, icon, children, count, end }: { to: string; icon: ReactNode; children: ReactNode; count?: number; end?: boolean }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        clsx(
          "group relative flex h-8 items-center gap-2.5 rounded-lg px-2.5 text-[13px] font-medium transition-colors",
          isActive ? "text-ink" : "text-[#4b5260] hover:bg-black/[0.035] hover:text-ink",
        )
      }
    >
      {({ isActive }) => (
        <>
          {isActive && (
            <motion.span layoutId="nav-pill" transition={{ type: "spring", stiffness: 420, damping: 34 }}
              className="absolute inset-0 rounded-lg bg-white shadow-[var(--shadow-card)] ring-1 ring-line" />
          )}
          <span className={clsx("relative transition-transform duration-300 group-hover:scale-110 [&>svg]:size-4", isActive ? "text-ink" : "text-[#6b7280]")}>{icon}</span>
          <span className="relative flex-1">{children}</span>
          {!!count && <span className="relative rounded-full bg-amber-100 px-1.5 text-[11px] font-semibold text-amber-800 tnum">{count}</span>}
        </>
      )}
    </NavLink>
  );
}

export function Shell() {
  const location = useLocation();
  const { data } = useQuery({ queryKey: ["rfps", "review-count"], queryFn: () => api.rfps({ status: "review" }), refetchInterval: 10_000 });
  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 flex h-screen w-[232px] shrink-0 flex-col border-r border-line bg-[#f3f4f6]/70 px-3 py-4">
        <Link to="/app" className="flex items-center gap-2.5 px-2">
          <Logo className="size-7" />
          <div className="leading-tight">
            <div className="text-[14px] font-semibold tracking-[-0.01em]">Tenderdesk</div>
            <div className="text-[11px] text-muted">Meridian Systems</div>
          </div>
        </Link>

        <Link to="/app/requests/new"
          className="mt-5 flex h-9 items-center justify-center gap-1.5 rounded-lg bg-ink text-[13px] font-medium text-white shadow-[0_1px_2px_rgb(0_0_0/0.2)] hover:bg-ink-soft">
          <Plus className="size-4" /> New request
        </Link>

        <nav className="mt-5 space-y-0.5">
          <NavItem to="/app" end icon={<LayoutDashboard />}>Overview</NavItem>
          <NavItem to="/app/requests" icon={<FileStack />} count={data?.length}>Requests</NavItem>
        </nav>
        <div className="mt-6 px-2.5 label !text-[10.5px]">Commercial data</div>
        <nav className="mt-2 space-y-0.5">
          <NavItem to="/app/catalogue" icon={<Boxes />}>Catalogue</NavItem>
          <NavItem to="/app/market" icon={<Radar />}>Market</NavItem>
          <NavItem to="/app/finance" icon={<Landmark />}>Tax &amp; currency</NavItem>
        </nav>
        <div className="mt-6 px-2.5 label !text-[10.5px]">System</div>
        <nav className="mt-2 space-y-0.5">
          <NavItem to="/app/models" icon={<BarChart3 />}>Models &amp; data</NavItem>
        </nav>

        <UserMenu />
      </aside>
      <main className="min-w-0 flex-1">
        <AnimatePresence mode="wait" initial={false}>
          <motion.div key={location.pathname.split("/").slice(0, 4).join("/")} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }} transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}>
            <Outlet />
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  );
}

export function PageHeader({ title, description, actions, breadcrumb }: { title: ReactNode; description?: ReactNode; actions?: ReactNode; breadcrumb?: ReactNode }) {
  return (
    <div className="border-b border-line bg-white">
      <div className="mx-auto flex max-w-[1320px] items-end justify-between gap-6 px-8 pb-5 pt-6">
        <div className="min-w-0">
          {breadcrumb && <div className="mb-2 text-[12px] text-muted">{breadcrumb}</div>}
          <h1 className="truncate text-[21px] font-semibold tracking-[-0.015em] text-ink">{title}</h1>
          {description && <div className="mt-1 text-[13px] text-muted">{description}</div>}
        </div>
        {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
      </div>
    </div>
  );
}

export function Page({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={clsx("mx-auto max-w-[1320px] px-8 py-6", className)}>{children}</div>;
}

function UserMenu() {
  const { user, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const h = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);
  if (!user) return null;
  const via = { password: "Username and password", google: "Google account", sso: "Single sign-on" }[user.provider];
  return (
    <div ref={ref} className="relative mt-auto">
      {open && (
        <div className="animate-fade-in absolute bottom-full left-0 right-0 mb-2 overflow-hidden rounded-xl border border-line bg-white shadow-[var(--shadow-pop)]">
          <div className="border-b border-line px-3.5 py-3">
            <div className="truncate text-[12.5px] font-medium">{user.name}</div>
            <div className="truncate text-[11.5px] text-muted">{user.email ?? `@${user.username}`}</div>
            <div className="mt-1 text-[11px] text-subtle">Signed in with {via}</div>
          </div>
          <Link to="/" className="flex items-center gap-2 px-3.5 py-2 text-[12.5px] text-ink-soft hover:bg-[#f6f7f9]"><Globe className="size-3.5" /> Product website</Link>
          <button onClick={signOut} className="flex w-full items-center gap-2 px-3.5 py-2 text-left text-[12.5px] text-rose-700 hover:bg-rose-50"><LogOut className="size-3.5" /> Sign out</button>
        </div>
      )}
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left hover:bg-black/[0.035]">
        <div className="grid size-8 place-items-center rounded-full bg-[#e7e0d2] text-[12px] font-semibold text-[#6b4e16]">{initials(user.name)}</div>
        <div className="min-w-0 flex-1 leading-tight">
          <div className="truncate text-[12.5px] font-medium">{user.name}</div>
          <div className="truncate text-[11px] text-muted">{user.title}</div>
        </div>
        <Settings2 className="size-4 text-subtle" />
      </button>
    </div>
  );
}
