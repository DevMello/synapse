// Shared TanStack Query client singleton. Exported so non-component code (e.g.
// Common.daemonName) can read cached query data synchronously via
// queryClient.getQueryData([...]). Mounted by main.tsx.
import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, refetchOnWindowFocus: false } },
});
