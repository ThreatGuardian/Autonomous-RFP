import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Building2, Check, ShieldCheck } from "lucide-react";
import { type FormEvent, useState } from "react";
import { Link, Navigate, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Logo } from "../../components/layout/Shell";
import { Spinner } from "../../components/ui";
import { auth } from "../../lib/api";
import { GoogleMark } from "./Login";

/**
 * Federated sign-in step. In production this screen is replaced by the identity
 * provider itself (Google OAuth consent or the organisation's SAML IdP); here it
 * collects the identity the provider would return and completes the session.
 */
export default function ProviderSignIn() {
  const { provider } = useParams();
  const [params] = useSearchParams();
  const next = params.get("next") || "/app";
  const navigate = useNavigate();
  const qc = useQueryClient();
  const google = provider === "google";
  const [email, setEmail] = useState(google ? "" : "");
  const [name, setName] = useState("");
  const [stage, setStage] = useState<"form" | "redirect">("form");
  const [error, setError] = useState<string | null>(null);

  const done = useMutation({
    mutationFn: () => auth.federated(google ? "google" : "sso", email, name || undefined),
    onSuccess: (u) => { qc.setQueryData(["me"], u); navigate(next, { replace: true }); },
    onError: (e: Error) => { setStage("form"); setError(e.message); },
  });

  if (provider !== "google" && provider !== "sso") return <Navigate to="/login" replace />;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) { setError("Enter a valid email address."); return; }
    setStage("redirect");
    setTimeout(() => done.mutate(), google ? 700 : 1300);
  };
  const domain = email.includes("@") ? email.split("@")[1] : "your organisation";

  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden bg-canvas px-4 py-10">
      <div className="bg-grid absolute inset-0 [mask-image:radial-gradient(60%_60%_at_50%_40%,#000,transparent)]" />
      <div className="animate-rise relative w-full max-w-[420px] rounded-2xl border border-line bg-white p-8 shadow-[var(--shadow-pop)]">
        <div className="flex items-center justify-center gap-4">
          <span className="grid size-12 place-items-center rounded-2xl border border-line bg-white shadow-[var(--shadow-card)]">
            {google ? <GoogleMark className="size-6" /> : <Building2 className="size-6 text-ink-soft" />}
          </span>
          <span className="flex gap-1">{[0, 1, 2].map((i) => <span key={i} className="size-1.5 animate-pulse-dot rounded-full bg-line-strong" style={{ animationDelay: `${i * 0.2}s` }} />)}</span>
          <span className="grid size-12 place-items-center rounded-2xl border border-line bg-white shadow-[var(--shadow-card)]"><Logo className="size-7" /></span>
        </div>

        {stage === "form" ? (
          <>
            <h1 className="mt-6 text-center text-[20px] font-semibold tracking-[-0.02em]">{google ? "Sign in with Google" : "Single sign-on"}</h1>
            <p className="mt-1.5 text-center text-[13px] text-muted">
              {google ? "Choose the Google account to use with Tenderdesk." : "Enter your work email and we'll send you to your organisation's identity provider."}
            </p>
            <form onSubmit={submit} className="mt-6 space-y-3">
              <label className="block"><span className="mb-1.5 block text-[12.5px] font-medium text-ink-soft">{google ? "Google account email" : "Work email"}</span>
                <input className="input h-11 rounded-xl" type="email" autoFocus value={email} onChange={(e) => setEmail(e.target.value)}
                  placeholder={google ? "you@gmail.com" : "you@meridiansystems.in"} /></label>
              {google && (
                <label className="block"><span className="mb-1.5 block text-[12.5px] font-medium text-ink-soft">Name <span className="font-normal text-subtle">(optional)</span></span>
                  <input className="input h-11 rounded-xl" value={name} onChange={(e) => setName(e.target.value)} placeholder="As shown on your account" /></label>
              )}
              {error && <div className="rounded-xl border border-rose-200 bg-rose-50 px-3.5 py-2.5 text-[12.5px] text-rose-800">{error}</div>}
              <button type="submit" className="group flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-ink text-[14px] font-medium text-white transition hover:bg-ink-soft">
                Continue <ArrowRight className="size-4 transition group-hover:translate-x-0.5" />
              </button>
            </form>
            <ul className="mt-6 space-y-2 border-t border-line pt-5 text-[12px] text-muted">
              {["Tenderdesk receives your name and email address only.", "No password is shared with Tenderdesk."].map((t) => (
                <li key={t} className="flex gap-2"><Check className="mt-0.5 size-3.5 text-emerald-600" />{t}</li>
              ))}
            </ul>
          </>
        ) : (
          <div className="py-8 text-center">
            <Spinner className="mx-auto size-6 text-ink" />
            <div className="mt-4 text-[15px] font-semibold">{google ? "Verifying your Google account" : `Redirecting to ${domain}`}</div>
            <div className="mt-1 flex items-center justify-center gap-1.5 text-[12.5px] text-muted"><ShieldCheck className="size-3.5" /> Secure connection</div>
          </div>
        )}
      </div>
      <Link to={`/login?next=${encodeURIComponent(next)}`} className="relative mt-6 inline-flex items-center gap-1.5 text-[12.5px] text-muted transition hover:text-ink">
        <ArrowLeft className="size-3.5" /> Other sign-in options
      </Link>
      <p className="relative mt-3 max-w-[420px] text-center text-[11.5px] text-subtle">Demonstration environment: this step stands in for the provider's own sign-in page.</p>
    </div>
  );
}
