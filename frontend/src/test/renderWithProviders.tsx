import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderOptions, type RenderResult } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { MemoryRouter, type MemoryRouterProps } from "react-router-dom";

import { AuthProvider } from "@/lib/auth/AuthContext";

interface ProvidersOptions {
  routerProps?: MemoryRouterProps;
  queryClient?: QueryClient;
  withAuth?: boolean;
}

export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 0 },
      mutations: { retry: false },
    },
  });
}

interface ProvidersProps {
  children: ReactNode;
}

export function renderWithProviders(
  ui: ReactElement,
  { routerProps, queryClient, withAuth = false, ...options }: ProvidersOptions & RenderOptions = {},
): RenderResult & { queryClient: QueryClient } {
  const qc = queryClient ?? makeQueryClient();

  function Providers({ children }: ProvidersProps) {
    const inner = withAuth ? <AuthProvider>{children}</AuthProvider> : children;
    return (
      <QueryClientProvider client={qc}>
        <MemoryRouter {...routerProps}>{inner}</MemoryRouter>
      </QueryClientProvider>
    );
  }

  return { ...render(ui, { wrapper: Providers, ...options }), queryClient: qc };
}
