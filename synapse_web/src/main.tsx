import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router-dom";

// Design system is loaded in order: Tailwind preflight first, then the three
// bespoke Synapse stylesheets (so the design wins over resets), then Tailwind
// component/utility layers last.
import "./styles/_tw-base.css";
import "./styles/colors_and_type.css";
import "./styles/effects.css";
import "./styles/app.css";
import "./styles/_tw-utils.css";

import { router } from "./router";

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, refetchOnWindowFocus: false } },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} future={{ v7_startTransition: true }} />
    </QueryClientProvider>
  </React.StrictMode>,
);
