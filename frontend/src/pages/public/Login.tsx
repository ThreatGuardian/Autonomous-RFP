import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { ArrowLeft, ArrowRight, Building2, Eye, EyeOff } from "lucide-react";
import { type FormEvent, type ReactNode, useEffect, useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { Logo } from "../../components/layout/Shell";
import { Spinner } from "../../components/ui";
import { auth as apiAuth, type User } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { firebaseAuth, firebaseConfigured, ssoProviderId } from "../../lib/firebase";

export function GoogleMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 48 48" className={className} aria-hidden>
      <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34.1 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z" />
      <path fill="#FF3D00" d="m6.3 14.7 6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34.1 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
      <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z" />
      <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z" />
    </svg>
  );
}

function Provider({ icon, children, onClick }: { icon: ReactNode; children: ReactNode; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick}
      className="group flex h-11 w-full items-center justify-center gap-2.5 rounded-xl border border-line-strong bg-white text-[13.5px] font-medium text-ink shadow-[var(--shadow-card)] transition hover:-translate-y-px hover:border-[#c9ced6] hover:bg-[#fafbfc] hover:shadow-[0_6px_16px_-8px_rgb(11_18_32/0.25)]">
      {icon}{children}
    </button>
  );
}

function AsidePanel() {
  const quotes = [
    { q: "We answered four tenders in the week our sales lead was on leave — each one priced and explained line by line.", who: "Commercial lead, IT reseller" },
    { q: "The below-cost warning alone saved us from two loss-making bids this quarter.", who: "Director, systems integrator" },
    { q: "Finance finally trusts the quote: every discount has a reason attached to it.", who: "Finance controller, SME distributor" },
  ];
  const [i, setI] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setI((v) => (v + 1) % quotes.length), 6000);
    return () => clearInterval(t);
  }, [quotes.length]);
  return (
    <div className="relative hidden overflow-hidden bg-ink text-white lg:flex lg:flex-col lg:justify-between lg:p-12">
      <div className="bg-grid-dark absolute inset-0 [mask-image:radial-gradient(80%_70%_at_70%_30%,#000,transparent)]" />
      <div className="absolute -right-24 top-10 size-96 rounded-full bg-[#e0a43a]/20 blur-3xl" />
      <div className="absolute -bottom-24 -left-16 size-80 rounded-full bg-[#2451d6]/25 blur-3xl" />

      <div className="relative flex items-center gap-2 text-[13px] text-white/70"><span className="size-1.5 rounded-full bg-[#e0a43a]" /> Tenderdesk for bid teams</div>

      <div className="relative">
        <div className="animate-float-a max-w-[380px] rounded-2xl border border-white/10 bg-white/[0.06] p-5 backdrop-blur-md">
          <div className="flex items-center justify-between text-[11px] uppercase tracking-[0.08em] text-white/50"><span>RFP-2026-0003</span><span>Awaiting review</span></div>
          <div className="mt-2 text-[16px] font-semibold">Harbourline Freight LLC</div>
          <div className="mt-4 grid grid-cols-3 gap-3">
            {[["AED 343,881", "quotation"], ["15.8%", "margin"], ["70%", "win chance"]].map(([v, l]) => (
              <div key={l}><div className="text-[15px] font-semibold tnum">{v}</div><div className="text-[11px] text-white/50">{l}</div></div>
            ))}
          </div>
          <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-white/10"><div className="h-full w-[70%] rounded-full bg-gradient-to-r from-[#c98a1b] to-[#f0c36a]" /></div>
        </div>
        <div className="animate-float-b ml-16 mt-4 max-w-[320px] rounded-2xl border border-white/10 bg-white/[0.06] p-4 text-[12.5px] leading-relaxed text-white/80 backdrop-blur-md">
          <span className="font-medium text-[#f0c36a]">Value differentiation · </span>Competitor 6.8% below our cost; price held, on-site deployment included.
        </div>
      </div>

      <figure className="relative max-w-[440px]">
        <blockquote key={i} className="animate-fade-in text-balance text-[19px] font-medium leading-snug tracking-[-0.01em]">“{quotes[i].q}”</blockquote>
        <figcaption className="mt-3 text-[13px] text-white/55">{quotes[i].who}</figcaption>
        <div className="mt-5 flex gap-1.5">
          {quotes.map((_, j) => (
            <button key={j} aria-label={`Quote ${j + 1}`} onClick={() => setI(j)} className={clsx("h-1 rounded-full transition-all", j === i ? "w-6 bg-white" : "w-3 bg-white/30 hover:bg-white/50")} />
          ))}
        </div>
      </figure>
    </div>
  );
}

export default function Login({ mode = "signin" }: { mode?: "signin" | "signup" }) {
  const { user, loading } = useAuth();
  const [params] = useSearchParams();
  const next = params.get("next") || "/app";
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [show, setShow] = useState(false);
  const [form, setForm] = useState({ name: "", username: "", email: "", password: "" });
  const [error, setError] = useState<string | null>(null);
  const signup = mode === "signup";

  const config = useQuery({ queryKey: ["auth-config"], queryFn: apiAuth.config, staleTime: Infinity });
  const firebaseReady = firebaseConfigured && Boolean(config.data?.firebase);
  const canSignUp = config.data?.signup ?? true;

  const finish = (u: User) => {
    qc.setQueryData(["me"], u);
    navigate(next, { replace: true });
  };

  const submit = useMutation({
    mutationFn: () => signup
      ? apiAuth.register({ name: form.name, username: form.username, email: form.email || undefined, password: form.password })
      : apiAuth.login(form.username, form.password),
    onSuccess: finish,
    onError: (e: Error) => setError(e.message),
  });

  // Google and SSO: the browser signs in with Firebase, the server verifies the ID token
  // and opens its own session. The Firebase session itself is not kept.
  const viaFirebase = async (provider: "google" | "sso") => {
    setError(null);
    try {
      const [auth, sdk] = await Promise.all([firebaseAuth(), import("firebase/auth")]);
      const chosen = provider === "google" ? new sdk.GoogleAuthProvider()
        : ssoProviderId!.startsWith("saml.") ? new sdk.SAMLAuthProvider(ssoProviderId!) : new sdk.OAuthProvider(ssoProviderId!);
      try {
        const cred = await sdk.signInWithPopup(auth, chosen);
        finish(await apiAuth.firebaseLogin(await cred.user.getIdToken()));
      } finally {
        await sdk.signOut(auth).catch(() => undefined);
      }
    } catch (e) {
      const code = (e as { code?: string }).code;
      if (code !== "auth/popup-closed-by-user" && code !== "auth/cancelled-popup-request") setError((e as Error).message);
    }
  };
  const goGoogle = () => viaFirebase("google");
  const goSSO = () => ssoProviderId && viaFirebase("sso");

  if (!loading && user) return <Navigate to={next} replace />;
  const onSubmit = (e: FormEvent) => { e.preventDefault(); setError(null); submit.mutate(); };
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });

  return (
    <div className="grid min-h-screen bg-white lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
      <div className="flex flex-col px-6 py-8 sm:px-12">
        <div className="flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2.5"><Logo className="size-7" /><span className="text-[15px] font-semibold">Tenderdesk</span></Link>
          <Link to="/" className="inline-flex items-center gap-1.5 text-[12.5px] text-muted transition hover:text-ink"><ArrowLeft className="size-3.5" /> Back to site</Link>
        </div>

        <div className="mx-auto flex w-full max-w-[380px] flex-1 flex-col justify-center py-12">
          <h1 className="animate-rise text-[28px] font-semibold tracking-[-0.025em]">{signup ? "Create your account" : "Welcome back"}</h1>
          <p className="animate-rise mt-1.5 text-[14px] text-muted" style={{ animationDelay: ".05s" }}>
            {signup ? "Start quoting RFPs with your team in minutes." : "Sign in to your bid desk to continue."}
          </p>

          {firebaseReady ? (
            <>
              <div className="animate-rise mt-8 space-y-2.5" style={{ animationDelay: ".1s" }}>
                <Provider icon={<GoogleMark className="size-[18px]" />} onClick={goGoogle}>Continue with Google</Provider>
                {ssoProviderId && <Provider icon={<Building2 className="size-[18px] text-ink-soft" />} onClick={goSSO}>Continue with SSO</Provider>}
              </div>
              <div className="my-6 flex items-center gap-3 text-[11.5px] uppercase tracking-[0.1em] text-subtle">
                <span className="h-px flex-1 bg-line" /> or {signup ? "sign up" : "sign in"} with username <span className="h-px flex-1 bg-line" />
              </div>
            </>
          ) : <div className="mt-8" />}

          <form onSubmit={onSubmit} className="animate-rise space-y-3.5" style={{ animationDelay: ".15s" }}>
            {signup && (
              <label className="block"><span className="mb-1.5 block text-[12.5px] font-medium text-ink-soft">Full name</span>
                <input className="input h-11 rounded-xl" autoComplete="name" required value={form.name} onChange={set("name")} placeholder="Aarav Kulkarni" /></label>
            )}
            <label className="block"><span className="mb-1.5 block text-[12.5px] font-medium text-ink-soft">{signup ? "Username" : "Username or email"}</span>
              <input className="input h-11 rounded-xl" autoComplete="username" required value={form.username} onChange={set("username")} placeholder={signup ? "aarav" : "priya"} autoFocus /></label>
            {signup && (
              <label className="block"><span className="mb-1.5 block text-[12.5px] font-medium text-ink-soft">Work email <span className="font-normal text-subtle">(optional)</span></span>
                <input className="input h-11 rounded-xl" type="email" autoComplete="email" value={form.email} onChange={set("email")} placeholder="you@company.com" /></label>
            )}
            <label className="block">
              <span className="mb-1.5 flex justify-between text-[12.5px] font-medium text-ink-soft">Password
                {signup && <span className="font-normal text-subtle">At least 10 characters</span>}</span>
              <div className="relative">
                <input className="input h-11 rounded-xl pr-10" type={show ? "text" : "password"} autoComplete={signup ? "new-password" : "current-password"}
                  required minLength={signup ? 10 : 1} value={form.password} onChange={set("password")} placeholder="••••••••" />
                <button type="button" onClick={() => setShow(!show)} aria-label={show ? "Hide password" : "Show password"}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded-md p-1 text-subtle transition hover:text-ink">{show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}</button>
              </div>
            </label>
            {error && <div className="animate-fade-in rounded-xl border border-rose-200 bg-rose-50 px-3.5 py-2.5 text-[12.5px] text-rose-800">{error}</div>}
            <button type="submit" disabled={submit.isPending}
              className="group mt-2 flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-ink text-[14px] font-medium text-white shadow-[0_8px_20px_-10px_rgb(11_18_32/0.7)] transition hover:bg-ink-soft disabled:opacity-60">
              {submit.isPending ? <Spinner className="size-4" /> : <>{signup ? "Create account" : "Sign in"} <ArrowRight className="size-4 transition group-hover:translate-x-0.5" /></>}
            </button>
          </form>

          {(canSignUp || signup) && <p className="mt-6 text-center text-[13px] text-muted">
            {signup ? "Already have an account? " : "New to Tenderdesk? "}
            <Link to={`${signup ? "/login" : "/signup"}${next !== "/app" ? `?next=${encodeURIComponent(next)}` : ""}`} className="font-medium text-ink underline decoration-line-strong underline-offset-4 transition hover:decoration-ink">
              {signup ? "Sign in" : "Create an account"}
            </Link>
          </p>}

        </div>

        <div className="text-[11.5px] text-subtle">© Tenderdesk</div>
      </div>
      <AsidePanel />
    </div>
  );
}
