import "@fontsource-variable/inter";
import "./index.css";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Shell } from "./components/layout/Shell";
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
        <Routes>
          <Route element={<Shell />}>
            <Route index element={<Overview />} />
            <Route path="requests" element={<Requests />} />
            <Route path="requests/new" element={<NewRequest />} />
            <Route path="requests/:id" element={<RequestDetail />} />
            <Route path="catalogue" element={<Catalogue />} />
            <Route path="market" element={<Market />} />
            <Route path="finance" element={<Finance />} />
            <Route path="models" element={<Models />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
