"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError } from "@/lib/api";

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 5_000,
            refetchOnWindowFocus: false,
            // Do not retry "not found", validation errors or an unreachable server (the banner covers that);
            // do retry once when the API blips.
            retry: (count, error) =>
              count < 1 && !(error instanceof ApiError && (error.unreachable || (error.status >= 400 && error.status < 500))),
          },
        },
      }),
  );
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
