import { QueryClient } from "@tanstack/react-query";

export function createCustomerQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: 1,
        refetchOnReconnect: true,
        refetchOnWindowFocus: false,
      },
      mutations: { retry: false },
    },
  });
}
