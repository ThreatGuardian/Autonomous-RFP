# Setup: keys and configuration

Tenderdesk runs without any keys: the agents fall back to their rule-based logic,
sign-in works with usernames and passwords, and exchange rates come from public
sources that need no key. Add the keys below to switch on the parts that need them.

| What | Needed for | Where it goes | Cost |
|---|---|---|---|
| **Anthropic API key** | The Claude agents (parser, pricing & competitor analysis, drafting) | `.env` → `ANTHROPIC_API_KEY` | Pay per use (see step 1.4) |
| **Firebase project** | "Continue with Google" and single sign-on | `.env` → `TD_FIREBASE_PROJECT_ID`, and `frontend/.env.local` | Free tier is enough |
| **Session secret** | Signing sign-in cookies (required in production) | `.env` → `TD_SECRET_KEY` | — |
| Market API key | Only if you run the mock market as a separate service | `.env` → `TD_MARKET_API_KEY` | — |
| Exchange rates | Nothing to do: Frankfurter (ECB) and open.er-api.com need no key | — | Free |

Start by copying the two example files:

```bash
cp .env.example .env                       # backend settings and keys
cp frontend/.env.example frontend/.env.local   # browser settings (Firebase)
```

`run.sh` and `run.ps1` read `.env` automatically; the web build reads
`frontend/.env.local`. Both files are listed in `.gitignore` — never commit them.

---

## 1. Anthropic API key (Claude agents)

1. Go to **https://console.anthropic.com** and sign up or sign in.
2. Open **Settings → Billing** and add a payment method or buy prepaid credits.
   API usage is billed separately from any Claude.ai subscription.
3. Open **Settings → API keys → Create key**. Name it (for example `tenderdesk-dev`),
   choose the workspace, and copy the key. It starts with `sk-ant-` and is shown
   only once.
4. Optional but recommended: in **Settings → Limits**, set a monthly spend limit for
   the workspace. Expect very roughly **USD 0.50–1.50 for a 10–15 page tender** with
   the default model (USD 4 / 20 per million input / output tokens): the parser reads
   the whole document once, and the pricing agent's tool loop resends its growing
   conversation each turn (cached, so the repeats are billed at the much lower
   cache-read rate). Short requests cost a fraction of that. Check the console's usage
   page for real figures; `TD_LLM_MODEL=claude-sonnet-5-5` roughly halves the cost.
5. Put the key in `.env`:

   ```bash
   ANTHROPIC_API_KEY=sk-ant-...
   TD_LLM=auto                 # use Claude whenever the key is present
   TD_LLM_MODEL=claude-opus-5-5
   ```

6. Restart the server and check: `GET /api/llm/status` should return
   `{"enabled": true, "model": "claude-opus-5-5", ...}`. Process a sample tender
   and open its **Activity** tab — each stage logs "Language model usage" with the
   tokens used; the Pricing tab shows the pricing analyst's assessment.

**If a call fails** (wrong key, no credit, network), the agent logs a warning and
continues with its rules — the request is still priced. `TD_LLM=on` keeps the same
fallback but makes the intent explicit; `TD_LLM=off` never calls the API.

**Measuring quality.** `python -m app.llm.evaluate --llm` (run in `backend/`) parses
the reference tenders with Claude and compares the items and products found with the
expected answers in `backend/evals/parser_gold.json`. Run it before and after changing
a prompt. It makes paid API calls.

---

## 2. Firebase (Google sign-in and SSO) — optional

Firebase handles the Google (or SAML/OIDC) sign-in popup in the browser. The server
then verifies the Firebase ID token against Google's public keys and opens its own
session; no service-account key is needed on the server.

1. Go to **https://console.firebase.google.com** → **Add project**. Choose a name;
   Google Analytics is not needed.
2. **Build → Authentication → Get started → Sign-in method** → enable **Google**,
   pick a support email and save.
3. **Authentication → Settings → Authorized domains**: `localhost` is there by
   default; add your production domain when you deploy.
4. **Project settings (gear icon) → General → Your apps → Web (`</>`)** → register an
   app (no hosting needed). Copy the values from the `firebaseConfig` shown.
5. Fill in `frontend/.env.local`:

   ```bash
   VITE_FIREBASE_API_KEY=AIza...
   VITE_FIREBASE_AUTH_DOMAIN=your-project.firebaseapp.com
   VITE_FIREBASE_PROJECT_ID=your-project
   VITE_FIREBASE_APP_ID=1:1234567890:web:abc123
   ```

6. Put the same project id in `.env` so the server accepts tokens from it:

   ```bash
   TD_FIREBASE_PROJECT_ID=your-project
   ```

7. Rebuild and restart (`./run.sh`). The sign-in page now shows **Continue with Google**.

**Single sign-on (optional).** SAML and OIDC providers require upgrading the Firebase
project to **Firebase Authentication with Identity Platform** (Authentication →
Settings). Then add the provider under **Sign-in method → Add new provider → SAML**
(or OpenID Connect) with your identity provider's details, note its provider id
(`saml.something` or `oidc.something`) and set it in `frontend/.env.local`:

```bash
VITE_FIREBASE_SSO_PROVIDER=saml.your-idp
```

**Account rules.** A Google sign-in creates an account the first time (when sign-up is
allowed). It joins an existing username/password account with the same email only if
the provider reports the email as verified.

---

## 3. Session secret

Sign-in cookies are signed with a secret. In development one is generated into the
`var` folder automatically. For production, generate one and set it:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

```bash
TD_SECRET_KEY=<the 64-character value>
```

Changing it signs everyone out.

---

## 4. Running in production

Set `TD_ENV=production`. The server then refuses to start unless `TD_SECRET_KEY` is
set (32+ characters), `TD_MARKET_API_KEY` is not the demo value and sign-in is
required. It also:

* sends cookies over HTTPS only (serve it behind HTTPS) and adds HSTS;
* turns off open sign-up (`TD_ALLOW_SIGNUP=1` to allow it) and never creates the demo account;
* hides the interactive API documentation at `/docs`.

Other settings worth reviewing: `TD_ALLOWED_ORIGINS` (extra browser origins allowed to
call the API; the server's own origin is always allowed), `TD_DATABASE_URL` (for
PostgreSQL) and `TD_VAR_DIR` (where documents and models are stored).

---

## 5. Demo account

For a local demonstration you can create the account `priya` / `tenderdesk`:

```bash
TD_DEMO_USER=1
```

It is never created in production. Otherwise, create an account from the sign-up page.

---

## 6. Checklist

- [ ] `.env` created from `.env.example`
- [ ] `ANTHROPIC_API_KEY` set and `/api/llm/status` shows `enabled: true`
- [ ] (optional) Firebase web config in `frontend/.env.local` and `TD_FIREBASE_PROJECT_ID` in `.env`
- [ ] (production) `TD_ENV=production`, `TD_SECRET_KEY`, `TD_MARKET_API_KEY`, HTTPS in front of the server
- [ ] Operating region set on the **Tax & currency** page
