import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "../../platform/auth/auth-context";
import {
  customerResourcePaths,
  type CreateGarageEntry,
  type GarageEntry,
} from "../../platform/api/customer-contract";
import { apiRequest } from "../../platform/api/request";
import { newIdempotencyKey } from "./idempotency";

export function useCreateGarageEntry() {
  const auth = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: CreateGarageEntry) => {
      if (!auth.credential) throw new Error("Authentication is required.");
      return apiRequest<GarageEntry>(customerResourcePaths.garage, {
        method: "POST",
        accessToken: auth.credential.accessToken,
        idempotencyKey: newIdempotencyKey("garage-create"),
        body: JSON.stringify(input),
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["customer", auth.credential?.subject, "garage"],
      });
    },
  });
}
