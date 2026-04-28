import { useState } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";

import { AuthProvider } from "@/lib/auth/AuthContext";
import { createQueryClient } from "@/lib/queryClient";
import { AppRoutes } from "@/routes/AppRoutes";

/**
 * Composizione provider: QueryClient → Router → Auth → Routes.
 *
 * AuthProvider è dentro Router perché usa `useNavigate` lato chiamate.
 * QueryClient esterno: i hook React Query funzionano anche per chiamate
 * non-route (es. tools di debug).
 */
export function App() {
  const [queryClient] = useState(() => createQueryClient());

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter
        future={{
          v7_startTransition: true,
          v7_relativeSplatPath: true,
        }}
      >
        <AuthProvider>
          <AppRoutes />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
