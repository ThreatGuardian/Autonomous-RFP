import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { BarChart3, Boxes, FileStack, Landmark, LayoutDashboard, Plus, Radar, Settings2 } from "lucide-react";
import type { ReactNode } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";
import { api } from "../../lib/api";

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
          "group flex h-8 items-center gap-2.5 rounded-lg px-2.5 text-[13px] font-medium transition-colors",
          isActive ? "bg-white text-ink shadow-[var(--shadow-card)] ring-1 ring-line" : "text-[#4b5260] hover:bg-black/[0.035] hover:text-ink",
        )
      }
    >
      <span className="text-[#6b7280] group-[.active]:text-ink [&>svg]:size-4">{icon}</span>
      <span className="flex-1">{children}</span>
      {!!count && <span className="rounded-full bg-amber-100 px-1.5 text-[11px] font-semibold text-amber-800 tnum">{count}</span>}
    </NavLink>
  );
}

export function Shell() {
  const { data } = useQuery({ queryKey: ["rfps", "review-count"], queryFn: () => api.rfps({ status: "review" }), refetchInterval: 10_000 });
  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 flex h-screen w-[232px] shrink-0 flex-col border-r border-line bg-[#f3f4f6]/70 px-3 py-4">
        <Link to="/" className="flex items-center gap-2.5 px-2">
          <Logo className="size-7" />
          <div className="leading-tight">
            <div className="text-[14px] font-semibold tracking-[-0.01em]">Tenderdesk</div>
            <div className="text-[11px] text-muted">Meridian Systems</div>
          </div>
        </Link>

        <Link to="/requests/new"
          className="mt-5 flex h-9 items-center justify-center gap-1.5 rounded-lg bg-ink text-[13px] font-medium text-white shadow-[0_1px_2px_rgb(0_0_0/0.2)] hover:bg-ink-soft">
          <Plus className="size-4" /> New request
        </Link>

        <nav className="mt-5 space-y-0.5">
          <NavItem to="/" end icon={<LayoutDashboard />}>Overview</NavItem>
          <NavItem to="/requests" icon={<FileStack />} count={data?.length}>Requests</NavItem>
        </nav>
        <div className="mt-6 px-2.5 label !text-[10.5px]">Commercial data</div>
        <nav className="mt-2 space-y-0.5">
          <NavItem to="/catalogue" icon={<Boxes />}>Catalogue</NavItem>
          <NavItem to="/market" icon={<Radar />}>Market</NavItem>
          <NavItem to="/finance" icon={<Landmark />}>Tax &amp; currency</NavItem>
        </nav>
        <div className="mt-6 px-2.5 label !text-[10.5px]">System</div>
        <nav className="mt-2 space-y-0.5">
          <NavItem to="/models" icon={<BarChart3 />}>Models &amp; data</NavItem>
        </nav>

        <div className="mt-auto flex items-center gap-2.5 rounded-lg px-2 py-2">
          <div className="grid size-8 place-items-center rounded-full bg-[#e7e0d2] text-[12px] font-semibold text-[#6b4e16]">PS</div>
          <div className="min-w-0 flex-1 leading-tight">
            <div className="truncate text-[12.5px] font-medium">Priya Shah</div>
            <div className="truncate text-[11px] text-muted">Commercial lead</div>
          </div>
          <Settings2 className="size-4 text-subtle" />
        </div>
      </aside>
      <main className="min-w-0 flex-1">
        <Outlet />
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
