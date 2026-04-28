import { QueryClient } from "@tanstack/react-query";

/** QueryClient singleton: condiviso tra App e tests via createQueryClient(). */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: 1,
        staleTime: 30_000,
        refetchOnWindowFocus: false,
      },
    },
  });
}
