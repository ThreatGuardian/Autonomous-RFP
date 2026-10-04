import type { Auth } from "firebase/auth";

/**
 * Firebase is optional. It is used only for "Continue with Google" and "Continue with SSO".
 * The web configuration comes from build-time environment variables (frontend/.env.local);
 * when they are missing those buttons are hidden and username/password sign-in still works.
 * The SDK is loaded on first use, so it adds nothing to the initial page load.
 */
const env = import.meta.env;
const options = {
  apiKey: env.VITE_FIREBASE_API_KEY,
  authDomain: env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: env.VITE_FIREBASE_PROJECT_ID,
  appId: env.VITE_FIREBASE_APP_ID,
};

export const firebaseConfigured = Boolean(options.apiKey && options.authDomain && options.projectId && options.appId);

/** Firebase provider id of the organisation's SAML or OIDC identity provider, e.g. "saml.acme". */
export const ssoProviderId: string | undefined = env.VITE_FIREBASE_SSO_PROVIDER || undefined;

let auth: Promise<Auth> | null = null;

export function firebaseAuth(): Promise<Auth> {
  if (!firebaseConfigured) return Promise.reject(new Error("Firebase sign-in is not configured"));
  auth ??= Promise.all([import("firebase/app"), import("firebase/auth")])
    .then(([app, fbAuth]) => fbAuth.getAuth(app.initializeApp(options)));
  return auth;
}
