import { type FirebaseOptions, initializeApp } from "firebase/app";
import { type Auth, getAuth } from "firebase/auth";

/**
 * Firebase is optional. It is used only for "Continue with Google" and "Continue with SSO".
 * The web configuration comes from build-time environment variables (frontend/.env.local);
 * when they are missing those buttons are hidden and username/password sign-in still works.
 */
const env = import.meta.env;
const options: FirebaseOptions = {
  apiKey: env.VITE_FIREBASE_API_KEY,
  authDomain: env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: env.VITE_FIREBASE_PROJECT_ID,
  appId: env.VITE_FIREBASE_APP_ID,
};

export const firebaseAuth: Auth | null =
  options.apiKey && options.authDomain && options.projectId && options.appId ? getAuth(initializeApp(options)) : null;

/** Firebase provider id of the organisation's SAML or OIDC identity provider, e.g. "saml.acme". */
export const ssoProviderId: string | undefined = env.VITE_FIREBASE_SSO_PROVIDER || undefined;
