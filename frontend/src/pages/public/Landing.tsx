import clsx from "clsx";
import {
  ArrowRight, BadgeCheck, Building2, Check, FileSearch, FileText, Globe2, Landmark, LineChart, Lock, Radar, Scale, ShieldCheck, Sparkle, Timer,
} from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Logo } from "../../components/layout/Shell";
import { useAuth } from "../../lib/auth";

function useReveal() {
  useEffect(() => {
    const els = document.querySelectorAll<HTMLElement>(".reveal");
    const io = new IntersectionObserver(
      (entries) => entries.forEach((e) => e.isIntersecting && e.target.classList.add("is-visible")),
      { threshold: 0.12 },
    );
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, []);
}

function Nav() {
  const { user } = useAuth();
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const h = () => setScrolled(window.scrollY > 8);
    h();
    window.addEventListener("scroll", h, { passive: true });
    return () => window.removeEventListener("scroll", h);
  }, []);
  return (
    <header className={clsx("fixed inset-x-0 top-0 z-40 transition-all duration-300", scrolled ? "border-b border-line bg-white/80 backdrop-blur-xl" : "bg-transparent")}>
      <div className="mx-auto flex h-16 max-w-[1200px] items-center justify-between px-6">
        <Link to="/" className="flex items-center gap-2.5"><Logo className="size-7" /><span className="text-[15px] font-semibold tracking-[-0.01em]">Tenderdesk</span></Link>
        <nav className="hidden items-center gap-1 md:flex">
          {[["Product", "#product"], ["How it works", "#how"], ["Pricing logic", "#pricing"], ["Trust", "#trust"]].map(([l, h]) => (
            <a key={h} href={h} className="rounded-lg px-3 py-2 text-[13.5px] text-ink-soft transition hover:bg-black/[0.04] hover:text-ink">{l}</a>
          ))}
        </nav>
        <div className="flex items-center gap-2">
          {user ? (
            <Link to="/app" className="group inline-flex h-9 items-center gap-1.5 rounded-lg bg-ink px-4 text-[13px] font-medium text-white transition hover:bg-ink-soft">
              Open console <ArrowRight className="size-3.5 transition group-hover:translate-x-0.5" />
            </Link>
          ) : (
            <>
              <Link to="/login" className="hidden h-9 items-center rounded-lg px-3.5 text-[13px] font-medium text-ink-soft transition hover:bg-black/[0.04] hover:text-ink sm:inline-flex">Sign in</Link>
              <Link to="/signup" className="group inline-flex h-9 items-center gap-1.5 rounded-lg bg-ink px-4 text-[13px] font-medium text-white shadow-[0_1px_2px_rgb(0_0_0/0.2)] transition hover:bg-ink-soft">
                Get started <ArrowRight className="size-3.5 transition group-hover:translate-x-0.5" />
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}

// ----------------------------------------------------------------------------- hero visual

function MiniRow({ name, sku, price, strategy, tone, p }: { name: string; sku: string; price: string; strategy: string; tone: string; p: number }) {
  return (
    <div className="grid grid-cols-[1fr_80px_110px] items-center gap-3 border-b border-line px-4 py-2.5 text-[11.5px] last:border-0 md:grid-cols-[1fr_88px_120px_130px]">
      <div className="min-w-0"><div className="truncate font-medium text-ink">{name}</div><div className="font-mono text-[10px] text-subtle">{sku}</div></div>
      <div className="text-right font-semibold tnum">{price}</div>
      <div className="flex items-center gap-2">
        <div className="h-1.5 flex-1 rounded-full bg-[#eceef1]"><div className="h-full rounded-full bg-emerald-600" style={{ width: `${p}%` }} /></div>
        <span className="w-7 text-right tnum text-muted">{p}%</span>
      </div>
      <span className={clsx("hidden justify-self-start rounded-md px-1.5 py-0.5 text-[10px] font-medium ring-1 ring-inset md:inline", tone)}>{strategy}</span>
    </div>
  );
}

const GOLD_CHIP = "bg-accent-soft text-[#8a5a0b] ring-[#f1dfb8]";

function HeroVisual() {
  return (
    <div className="relative mx-auto mt-16 max-w-[1040px] px-4 md:px-0">
      <div className="absolute -inset-x-10 -top-10 bottom-0 -z-10 rounded-[40px] bg-[radial-gradient(60%_60%_at_50%_30%,rgba(224,164,58,0.18),transparent_70%)]" />
      <div className="animate-rise overflow-hidden rounded-2xl border border-line bg-white shadow-[0_40px_80px_-24px_rgb(11_18_32/0.28),0_8px_24px_-8px_rgb(11_18_32/0.12)]" style={{ animationDelay: ".25s" }}>
        <div className="flex items-center gap-2 border-b border-line bg-[#fafbfc] px-4 py-2.5">
          <span className="size-2.5 rounded-full bg-[#e5e7eb]" /><span className="size-2.5 rounded-full bg-[#e5e7eb]" /><span className="size-2.5 rounded-full bg-[#e5e7eb]" />
          <div className="mx-auto rounded-md bg-white px-3 py-0.5 text-[11px] text-subtle ring-1 ring-line">tenderdesk · requests · RFP-2026-0003</div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-[180px_1fr]">
          <div className="hidden border-r border-line bg-[#f7f8f9] p-3 md:block">
            {["Overview", "Requests", "Catalogue", "Market", "Tax & currency"].map((n, i) => (
              <div key={n} className={clsx("mb-1 rounded-md px-2.5 py-1.5 text-[11.5px]", i === 1 ? "bg-white font-medium text-ink shadow-[var(--shadow-card)] ring-1 ring-line" : "text-muted")}>{n}</div>
            ))}
          </div>
          <div className="p-4 text-left">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="text-[10.5px] text-subtle">Harbourline Freight LLC · Dubai</div>
                <div className="text-[15px] font-semibold tracking-[-0.01em]">Regional office fit-out</div>
              </div>
              <div className="flex gap-1.5">
                <span className="rounded-md border border-line px-2 py-1 text-[10.5px] text-ink-soft">Quotation</span>
                <span className="rounded-md bg-emerald-700 px-2 py-1 text-[10.5px] font-medium text-white">Approve</span>
              </div>
            </div>
            <div className="mt-3 grid grid-cols-5 overflow-hidden rounded-lg border border-line">
              {["Intake", "Costing", "Strategy", "Tax", "Drafting"].map((s, i) => (
                <div key={s} className={clsx("flex items-center gap-1.5 px-2.5 py-2 text-[10.5px]", i && "border-l border-line")}>
                  <span className="grid size-3.5 shrink-0 place-items-center rounded-full bg-emerald-600 text-white"><Check className="size-2.5" strokeWidth={3} /></span>
                  <span className="truncate">{s}</span>
                </div>
              ))}
            </div>
            <div className="mt-3 overflow-hidden rounded-lg border border-line">
              <MiniRow name="HP Pro Tower 280 G9 (Core i5, 16 GB)" sku="DCC-DT-201" price="₹46,583" strategy="Value differentiation" tone={GOLD_CHIP} p={65} />
              <MiniRow name="Logitech H390 USB Headset" sku="DCC-AU-601" price="₹1,837" strategy="Value differentiation" tone={GOLD_CHIP} p={78} />
              <MiniRow name="ZOTAC GeForce RTX 4060 8 GB" sku="DCC-CP-701" price="₹26,224" strategy="Competitive match" tone="bg-[#eef3ff] text-[#2146b8] ring-[#d9e3ff]" p={68} />
              <MiniRow name="LG 24MP400 24-inch IPS Monitor" sku="DCC-MN-403" price="₹7,533" strategy="Margin capture" tone="bg-[#ecf8f1] text-[#136c3f] ring-[#cdebd9]" p={87} />
            </div>
          </div>
        </div>
      </div>

      {/* floating insight cards */}
      <div className="animate-float-a absolute -left-4 top-[46%] hidden w-[270px] rounded-xl border border-line bg-white p-4 text-left shadow-[var(--shadow-pop)] lg:block xl:-left-20">
        <div className="flex items-center gap-2 text-[11px] font-medium text-rose-700"><span className="size-1.5 rounded-full bg-rose-600" />Competitor 6.8% below our cost</div>
        <div className="mt-2 text-[12.5px] font-semibold leading-snug text-ink">Matching would lose ₹2,10,095 on this line.</div>
        <div className="mt-1.5 text-[11.5px] leading-relaxed text-muted">Held at ₹82,900 and included on-site deployment, worth ₹2,500 a unit, instead.</div>
      </div>
      <div className="animate-float-b absolute -right-4 top-[16%] hidden w-[210px] rounded-xl border border-line bg-white p-4 text-left shadow-[var(--shadow-pop)] lg:block xl:-right-16">
        <div className="text-[10.5px] font-medium uppercase tracking-[0.06em] text-muted">Win probability</div>
        <div className="mt-2 flex items-center gap-3">
          <svg viewBox="0 0 36 36" className="size-12 -rotate-90">
            <circle cx="18" cy="18" r="15" fill="none" stroke="#eceef1" strokeWidth="4" />
            <circle cx="18" cy="18" r="15" fill="none" stroke="#0b1220" strokeWidth="4" strokeLinecap="round" strokeDasharray={`${0.7 * 94.2} 94.2`} />
          </svg>
          <div><div className="text-[20px] font-semibold tnum">70%</div><div className="text-[11px] text-muted">revenue-weighted</div></div>
        </div>
      </div>
      <div className="animate-float-a absolute -bottom-6 right-10 hidden items-center gap-3 rounded-xl border border-line bg-white px-4 py-3 text-left shadow-[var(--shadow-pop)] md:flex" style={{ animationDelay: "1.2s" }}>
        <span className="grid size-8 place-items-center rounded-full bg-emerald-50 text-emerald-700"><FileText className="size-4" /></span>
        <div><div className="text-[12.5px] font-semibold">Quotation ready · AED 343,881</div><div className="text-[11px] text-muted">5% VAT applied · drafted in 3.1 s</div></div>
      </div>
    </div>
  );
}

// ----------------------------------------------------------------------------- sections

function Eyebrow({ children }: { children: ReactNode }) {
  return <div className="text-[12px] font-semibold uppercase tracking-[0.14em] text-accent">{children}</div>;
}

function Feature({ icon, title, text, children, className, delay = 0 }: {
  icon: ReactNode; title: string; text: string; children?: ReactNode; className?: string; delay?: number;
}) {
  return (
    <div style={{ transitionDelay: `${delay}ms` }}
      className={clsx("reveal group relative overflow-hidden rounded-2xl border border-line bg-white p-6 transition duration-300 hover:-translate-y-1 hover:border-[#e2cfa6] hover:shadow-[0_24px_48px_-20px_rgb(11_18_32/0.22)]", className)}>
      <div className="pointer-events-none absolute -right-16 -top-16 size-40 rounded-full bg-[#e0a43a]/0 blur-2xl transition duration-500 group-hover:bg-[#e0a43a]/15" />
      <div className="grid size-10 place-items-center rounded-xl bg-[#f3f4f6] text-ink transition duration-300 group-hover:bg-ink group-hover:text-white [&>svg]:size-[18px]">{icon}</div>
      <h3 className="mt-4 text-[16px] font-semibold tracking-[-0.01em]">{title}</h3>
      <p className="mt-1.5 text-[13.5px] leading-relaxed text-muted">{text}</p>
      {children && <div className="mt-5">{children}</div>}
    </div>
  );
}

function PricingDemo() {
  const [mode, setMode] = useState<"match" | "value">("value");
  const match = mode === "match";
  return (
    <div className="reveal rounded-2xl border border-line bg-white p-6 shadow-[0_24px_60px_-28px_rgb(11_18_32/0.3)]">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><div className="text-[12px] text-muted">Dell Latitude 5450 · 45 units · Dubai</div><div className="text-[15px] font-semibold">Lowest competitor: ₹63,831</div></div>
        <div className="inline-flex rounded-lg border border-line-strong bg-[#f3f4f6] p-0.5">
          {(["match", "value"] as const).map((m) => (
            <button key={m} onClick={() => setMode(m)}
              className={clsx("h-8 rounded-md px-3 text-[12px] font-medium transition", mode === m ? "bg-white text-ink shadow-[var(--shadow-card)]" : "text-muted hover:text-ink")}>
              {m === "match" ? "Match the price" : "Tenderdesk"}
            </button>
          ))}
        </div>
      </div>
      <div className="mt-6 grid grid-cols-3 gap-3">
        {[
          ["Unit price", match ? "₹63,831" : "₹82,900"],
          ["Margin", match ? "−7.3%" : "16.8%"],
          ["Expected profit", match ? "−₹2.01 L" : "₹4.07 L"],
        ].map(([k, v]) => (
          <div key={k} className="rounded-xl border border-line bg-[#fafbfc] px-4 py-3">
            <div className="text-[11px] uppercase tracking-[0.06em] text-muted">{k}</div>
            <div className={clsx("mt-1 text-[19px] font-semibold tnum transition-colors duration-300", match && k !== "Unit price" ? "text-rose-700" : "text-ink")}>{v}</div>
          </div>
        ))}
      </div>
      <div className="mt-5">
        <div className="mb-1.5 flex justify-between text-[12px]"><span className="text-muted">Modelled win probability</span><span className="font-medium tnum">{match ? "96%" : "65%"}</span></div>
        <div className="h-2 overflow-hidden rounded-full bg-[#eceef1]">
          <div className={clsx("h-full rounded-full transition-all duration-700", match ? "bg-rose-500" : "bg-ink")} style={{ width: match ? "96%" : "65%" }} />
        </div>
      </div>
      <div className={clsx("mt-5 rounded-xl px-4 py-3 text-[13px] leading-relaxed transition-colors duration-300", match ? "bg-rose-50 text-rose-900" : "bg-accent-soft text-[#6b4e16]")}>
        {match
          ? "Winning at this price means selling 45 laptops below landed cost — a ₹2.1 lakh loss on one line."
          : "Price held above the margin floor. On-site deployment and imaging, worth ₹2,500 a unit to the client, is included at no charge."}
      </div>
    </div>
  );
}

export default function Landing() {
  useReveal();
  const { user } = useAuth();
  const primary = user ? "/app" : "/signup";
  return (
    <div className="min-h-screen bg-white text-ink">
      <Nav />

      {/* HERO */}
      <section className="relative overflow-hidden pb-28 pt-36">
        <div className="bg-grid absolute inset-0 -z-10 [mask-image:radial-gradient(70%_60%_at_50%_0%,#000_40%,transparent_100%)]" />
        <div className="mx-auto max-w-[1200px] px-6 text-center">
          <Link to={primary} className="animate-rise group inline-flex items-center gap-2 rounded-full border border-line bg-white/80 px-3 py-1 text-[12.5px] text-ink-soft shadow-[var(--shadow-card)] backdrop-blur transition hover:border-[#e2cfa6]">
            <span className="size-1.5 rounded-full bg-accent" /> Built for SMEs that win business through RFPs
            <ArrowRight className="size-3 text-muted transition group-hover:translate-x-0.5" />
          </Link>
          <h1 className="animate-rise text-balance mx-auto mt-6 max-w-[900px] text-[44px] font-semibold leading-[1.05] tracking-[-0.035em] md:text-[64px]" style={{ animationDelay: ".05s" }}>
            Answer every RFP with a quotation that <span className="gold-text">wins on value</span>, in minutes.
          </h1>
          <p className="animate-rise text-balance mx-auto mt-6 max-w-[640px] text-[17px] leading-relaxed text-muted" style={{ animationDelay: ".12s" }}>
            Tenderdesk reads the request, checks your cost and stock, studies competitor prices and drafts a branded quotation — with the reasoning behind every price. You review, adjust and send.
          </p>
          <div className="animate-rise mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row" style={{ animationDelay: ".18s" }}>
            <Link to={primary} className="group inline-flex h-11 items-center gap-2 rounded-xl bg-ink px-6 text-[14px] font-medium text-white shadow-[0_8px_24px_-8px_rgb(11_18_32/0.6)] transition hover:-translate-y-0.5 hover:bg-ink-soft">
              {user ? "Open the console" : "Get started"} <ArrowRight className="size-4 transition group-hover:translate-x-0.5" />
            </Link>
            <a href="#how" className="inline-flex h-11 items-center gap-2 rounded-xl border border-line-strong bg-white px-6 text-[14px] font-medium text-ink transition hover:-translate-y-0.5 hover:bg-[#fafbfc]">See how it works</a>
          </div>
          <div className="animate-rise mt-5 flex items-center justify-center gap-5 text-[12.5px] text-muted" style={{ animationDelay: ".22s" }}>
            {["PDF, Word or pasted text", "Every price explained", "You approve before anything is sent"].map((t) => (
              <span key={t} className="hidden items-center gap-1.5 sm:inline-flex"><Check className="size-3.5 text-emerald-600" />{t}</span>
            ))}
          </div>
        </div>
        <HeroVisual />
      </section>

      {/* CLIENTS */}
      <section className="border-y border-line bg-[#fafbfc] py-8">
        <div className="mx-auto flex max-w-[1200px] flex-wrap items-center justify-center gap-x-12 gap-y-4 px-6 text-[14px] font-semibold tracking-[-0.01em] text-[#9aa1ad]">
          <span className="text-[11px] font-medium uppercase tracking-[0.14em] text-subtle">Quoting for</span>
          {["Sahyadri Institute", "Kaveri Health", "Harbourline Freight", "Lionsgate Analytics", "Rheinland Präzision", "Cedar Valley USD"].map((n) => (
            <span key={n} className="transition hover:text-ink">{n}</span>
          ))}
        </div>
      </section>

      {/* PRODUCT */}
      <section id="product" className="scroll-mt-20 py-28">
        <div className="mx-auto max-w-[1200px] px-6">
          <div className="reveal max-w-[640px]">
            <Eyebrow>Product</Eyebrow>
            <h2 className="mt-3 text-[36px] font-semibold leading-tight tracking-[-0.03em]">Everything a bid desk does, done before your coffee cools.</h2>
            <p className="mt-4 text-[15.5px] leading-relaxed text-muted">Five specialised stages work through each request in sequence. Several requests run side by side, so a busy week no longer means a missed deadline.</p>
          </div>
          <div className="mt-14 grid grid-cols-1 gap-5 md:grid-cols-6">
            <Feature className="md:col-span-3" icon={<FileSearch />} title="Reads any request"
              text="Client, delivery location, currency, deadlines, terms and every requested item with its specification — from PDF, Word or pasted text.">
              <div className="flex flex-wrap gap-1.5 text-[11.5px]">
                {["60 × laptops · 16 GB · 512 GB SSD", "Due 10 Oct", "Net 45", "36-month warranty", "INR · Pune"].map((c) => (
                  <span key={c} className="rounded-md bg-[#f3f4f6] px-2 py-1 text-ink-soft transition group-hover:bg-[#fbf3e4]">{c}</span>
                ))}
              </div>
            </Feature>
            <Feature className="md:col-span-3" icon={<Radar />} title="Watches the market" delay={80}
              text="Competitor offers are gathered for every line and converted into your currency, so you see exactly where you stand.">
              <div className="space-y-1.5">
                {([["GlobalSource", 76, true], ["Apex Distributors", 78, true], ["Your price", 91, false], ["Brightline Tech", 99, false]] as const).map(([n, w, below]) => (
                  <div key={n} className="flex items-center gap-2 text-[11.5px]">
                    <span className={clsx("w-28", n === "Your price" ? "font-medium text-ink" : "text-muted")}>{n}</span>
                    <div className="h-1.5 flex-1 rounded-full bg-[#eceef1]">
                      <div className={clsx("h-full rounded-full transition-all duration-700", below ? "bg-rose-500" : n === "Your price" ? "bg-[#c98a1b]" : "bg-ink")} style={{ width: `${w}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            </Feature>
            <Feature className="md:col-span-2" icon={<Scale />} title="Never sells at a loss"
              text="When a rival goes below your cost, Tenderdesk holds a compliant price and competes on warranty and service instead." />
            <Feature className="md:col-span-2" icon={<Landmark />} title="Right currency, right tax" delay={80}
              text="Live exchange rates, GST and IGST, VAT, US sales tax, export zero-rating and reverse charge — applied automatically." />
            <Feature className="md:col-span-2" icon={<FileText />} title="Documents that close" delay={160}
              text="A branded quotation for the client, a pricing memo for your team and a bid report for leadership." />
          </div>
        </div>
      </section>

      {/* HOW */}
      <section id="how" className="scroll-mt-20 bg-[#fafbfc] py-28">
        <div className="mx-auto max-w-[1200px] px-6">
          <div className="reveal mx-auto max-w-[620px] text-center">
            <Eyebrow>How it works</Eyebrow>
            <h2 className="mt-3 text-[36px] font-semibold leading-tight tracking-[-0.03em]">From request to ready-to-send in five steps.</h2>
          </div>
          <ol className="relative mt-16 grid grid-cols-1 gap-8 md:grid-cols-5 md:gap-6">
            <div className="absolute left-[10%] right-[10%] top-6 hidden h-px bg-gradient-to-r from-transparent via-[#d5d9e0] to-transparent md:block" />
            {([
              [<FileSearch key="a" />, "Intake", "Items, specs, dates and terms are extracted and matched to your catalogue."],
              [<Building2 key="b" />, "Costing", "Landed cost, margin floor, volume tier, stock and lead time."],
              [<LineChart key="c" />, "Strategy", "Each line priced for the best expected profit within your policy."],
              [<Globe2 key="d" />, "Currency & tax", "Converted and taxed correctly for the client's jurisdiction."],
              [<BadgeCheck key="e" />, "Review & send", "Adjust anything, approve, and issue the final quotation."],
            ] as const).map(([icon, title, text], i) => (
              <li key={title} className="reveal group relative text-center" style={{ transitionDelay: `${i * 80}ms` }}>
                <div className="relative mx-auto grid size-12 place-items-center rounded-2xl border border-line bg-white text-ink shadow-[var(--shadow-card)] transition duration-300 group-hover:-translate-y-1 group-hover:border-[#e2cfa6] group-hover:shadow-[0_12px_24px_-12px_rgb(11_18_32/0.3)] [&>svg]:size-5">
                  {icon}
                  <span className="absolute -right-2 -top-2 grid size-5 place-items-center rounded-full bg-ink text-[10.5px] font-semibold text-white">{i + 1}</span>
                </div>
                <div className="mt-4 text-[15px] font-semibold">{title}</div>
                <p className="mx-auto mt-1.5 max-w-[210px] text-[13px] leading-relaxed text-muted">{text}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* PRICING LOGIC */}
      <section id="pricing" className="scroll-mt-20 py-28">
        <div className="mx-auto grid max-w-[1200px] grid-cols-1 items-center gap-14 px-6 lg:grid-cols-2">
          <div className="reveal">
            <Eyebrow>Pricing logic</Eyebrow>
            <h2 className="mt-3 text-[36px] font-semibold leading-tight tracking-[-0.03em]">When a competitor goes below your cost, you don't follow them down.</h2>
            <p className="mt-4 text-[15.5px] leading-relaxed text-muted">Tenderdesk models how buyers weigh price, warranty and lead time, then picks the offer with the best expected profit — never one below your margin floor.</p>
            <ul className="mt-7 space-y-3.5">
              {[
                "Every line shows the market, your cost basis and the alternatives considered.",
                "Free warranty or services are bundled when they win more than a price cut would.",
                "Tender rules matter: lowest-price awards are weighted more heavily than value-based ones.",
              ].map((t) => (
                <li key={t} className="flex gap-3 text-[14px] text-ink-soft">
                  <span className="mt-0.5 grid size-5 shrink-0 place-items-center rounded-full bg-accent-soft text-accent"><Check className="size-3" strokeWidth={3} /></span>{t}
                </li>
              ))}
            </ul>
            <p className="mt-6 text-[12.5px] text-subtle">Try it: switch between the two offers on the right.</p>
          </div>
          <PricingDemo />
        </div>
      </section>

      {/* STATS */}
      <section className="relative overflow-hidden bg-ink py-20 text-white">
        <div className="bg-grid-dark absolute inset-0 [mask-image:radial-gradient(60%_80%_at_50%_50%,#000,transparent)]" />
        <div className="relative mx-auto grid max-w-[1200px] grid-cols-2 gap-10 px-6 md:grid-cols-4">
          {[["< 5 s", "from upload to draft quotation"], ["30", "countries with tax rules and currencies"], ["3", "documents per bid: quotation, memo, report"], ["0", "lines quoted below the margin floor"]].map(([v, l], i) => (
            <div key={l} className="reveal" style={{ transitionDelay: `${i * 80}ms` }}>
              <div className="text-[40px] font-semibold leading-none tracking-[-0.03em] text-[#e0a43a]">{v}</div>
              <div className="mt-3 text-[13.5px] leading-relaxed text-white/60">{l}</div>
            </div>
          ))}
        </div>
      </section>

      {/* TRUST */}
      <section id="trust" className="scroll-mt-20 py-28">
        <div className="mx-auto max-w-[1200px] px-6">
          <div className="reveal max-w-[620px]">
            <Eyebrow>Trust</Eyebrow>
            <h2 className="mt-3 text-[36px] font-semibold leading-tight tracking-[-0.03em]">Every number can be explained. Nothing leaves without you.</h2>
          </div>
          <div className="mt-12 grid grid-cols-1 gap-5 md:grid-cols-3">
            <Feature icon={<Timer />} title="A complete decision log" text="Each stage records what it observed and decided, with timings. Reviewers see exactly why a price is what it is." />
            <Feature icon={<ShieldCheck />} title="Approval before sending" delay={80} text="Drafts carry a watermark until a named reviewer approves. Every change and approval is recorded." />
            <Feature icon={<Lock />} title="Your data stays yours" delay={160} text="Runs on your own infrastructure with your own pricing database. No request text is shared with outside services." />
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="px-6 pb-24">
        <div className="reveal relative mx-auto max-w-[1200px] overflow-hidden rounded-3xl bg-ink px-8 py-16 text-center text-white md:px-16">
          <div className="absolute -right-24 -top-24 size-80 rounded-full bg-[#e0a43a]/20 blur-3xl" />
          <div className="absolute -bottom-32 -left-20 size-80 rounded-full bg-[#2451d6]/20 blur-3xl" />
          <Sparkle className="relative mx-auto size-6 text-[#e0a43a]" />
          <h2 className="text-balance relative mx-auto mt-4 max-w-[640px] text-[34px] font-semibold leading-tight tracking-[-0.03em]">Your next RFP could be quoted before lunch.</h2>
          <p className="relative mx-auto mt-3 max-w-[520px] text-[15px] text-white/65">Sign in, drop in a request and review a priced, tax-correct quotation in a few seconds.</p>
          <div className="relative mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Link to={primary} className="group inline-flex h-11 items-center gap-2 rounded-xl bg-white px-6 text-[14px] font-medium text-ink transition hover:-translate-y-0.5">
              {user ? "Open the console" : "Get started"} <ArrowRight className="size-4 transition group-hover:translate-x-0.5" />
            </Link>
            {!user && <Link to="/login" className="inline-flex h-11 items-center rounded-xl border border-white/20 px-6 text-[14px] font-medium text-white transition hover:bg-white/10">Sign in</Link>}
          </div>
        </div>
      </section>

      <footer className="border-t border-line py-10">
        <div className="mx-auto flex max-w-[1200px] flex-col items-center justify-between gap-4 px-6 text-[12.5px] text-muted md:flex-row">
          <div className="flex items-center gap-2"><Logo className="size-5" /><span className="font-medium text-ink">Tenderdesk</span><span>· RFP response and competitive quotation</span></div>
          <div className="flex gap-6">
            <a href="#product" className="hover:text-ink">Product</a>
            <a href="#how" className="hover:text-ink">How it works</a>
            <Link to="/login" className="hover:text-ink">Sign in</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
