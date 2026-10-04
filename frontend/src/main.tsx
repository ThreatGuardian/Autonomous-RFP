import "@fontsource-variable/inter";
import "@fontsource-variable/source-serif-4";
import "./index.css";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "motion/react";
import { lazy, StrictMode, Suspense } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Shell } from "./components/layout/Shell";
import { AuthProvider, RequireAuth } from "./lib/auth";
import { Spinner } from "./components/ui";

// Each page loads on first visit, so the sign-in page does not download the console.
const Landing = lazy(() => import("./pages/public/Landing"));
const Login = lazy(() => import("./pages/public/Login"));
const Catalogue = lazy(() => import("./pages/Catalogue"));
const Finance = lazy(() => import("./pages/Finance"));
const Market = lazy(() => import("./pages/Market"));
const NewRequest = lazy(() => import("./pages/NewRequest"));
const Overview = lazy(() => import("./pages/Overview"));
const Requests = lazy(() => import("./pages/Requests"));
const RequestDetail = lazy(() => import("./pages/request/RequestDetail"));
const ReportEditor = lazy(() => import("./pages/report/ReportEditor"));

const loading = <div className="grid min-h-[40vh] place-items-center"><Spinner className="size-5 text-muted" /></div>;

const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 2000, retry: 1, refetchOnWindowFocus: false } } });

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      {/* Animations follow the operating system's reduced-motion setting. */}
      <MotionConfig reducedMotion="user">
        <BrowserRouter>
          <AuthProvider>
            <Suspense fallback={loading}>
              <Routes>
                <Route index element={<Landing />} />
                <Route path="login" element={<Login />} />
                <Route path="signup" element={<Login mode="signup" />} />
                <Route path="login/:provider" element={<Navigate to="/login" replace />} />
                <Route path="app" element={<RequireAuth><Shell /></RequireAuth>}>
                  <Route index element={<Overview />} />
                  <Route path="requests" element={<Requests />} />
                  <Route path="requests/new" element={<NewRequest />} />
                  <Route path="requests/:id" element={<RequestDetail />} />
                  <Route path="catalogue" element={<Catalogue />} />
                  <Route path="market" element={<Market />} />
                  <Route path="finance" element={<Finance />} />
                  <Route path="models" element={<Navigate to="/app" replace />} />
                </Route>
                <Route path="app/requests/:id/report" element={<RequireAuth><ReportEditor /></RequireAuth>} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </Suspense>
          </AuthProvider>
        </BrowserRouter>
      </MotionConfig>
    </QueryClientProvider>
  </StrictMode>,
);
