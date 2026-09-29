import "@fontsource-variable/inter";
import "./index.css";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Shell } from "./components/layout/Shell";
import { AuthProvider, RequireAuth } from "./lib/auth";
import Landing from "./pages/public/Landing";
import Login from "./pages/public/Login";
import ProviderSignIn from "./pages/public/ProviderSignIn";
import Catalogue from "./pages/Catalogue";
import Finance from "./pages/Finance";
import Market from "./pages/Market";
import Models from "./pages/Models";
import NewRequest from "./pages/NewRequest";
import Overview from "./pages/Overview";
import Requests from "./pages/Requests";
import RequestDetail from "./pages/request/RequestDetail";

const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 2000, retry: 1, refetchOnWindowFocus: false } } });

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route index element={<Landing />} />
            <Route path="login" element={<Login />} />
            <Route path="signup" element={<Login mode="signup" />} />
            <Route path="login/:provider" element={<ProviderSignIn />} />
            <Route path="app" element={<RequireAuth><Shell /></RequireAuth>}>
              <Route index element={<Overview />} />
              <Route path="requests" element={<Requests />} />
              <Route path="requests/new" element={<NewRequest />} />
              <Route path="requests/:id" element={<RequestDetail />} />
              <Route path="catalogue" element={<Catalogue />} />
              <Route path="market" element={<Market />} />
              <Route path="finance" element={<Finance />} />
              <Route path="models" element={<Models />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
