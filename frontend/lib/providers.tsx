"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { useState, type ReactNode } from "react";
import { Toaster } from "@/components/ui/sonner";

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(() => 
    new QueryClient({
      defaultOptions: {
        queries: {
          // Default to 5 minutes stale time for better UX
          staleTime: 1000 * 60 * 5,
          // Cache data for 10 minutes
          gcTime: 1000 * 60 * 10,
          // Retry failed requests once
          retry: 1,
          // Don't refetch on window focus for most queries
          refetchOnWindowFocus: false,
        },
        mutations: {
          retry: 1,
        },
      },
    })
  );

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider
        attribute="class"
        defaultTheme="light"
        enableSystem={false}
        disableTransitionOnChange
      >
        {children}
        <Toaster
          position="top-right"
          expand={false}
          richColors
          closeButton
        />
      </ThemeProvider>
    </QueryClientProvider>
  );
}
