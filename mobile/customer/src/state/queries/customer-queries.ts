import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../../platform/auth/auth-context";
import {
  customerResourcePaths,
  type CustomerConsents,
  type CustomerGarage,
  type CustomerProfile,
  type CustomerSecurity,
  type CustomerSessions,
  type CustomerDataRequests,
  type VehicleModels,
} from "../../platform/api/customer-contract";
import { apiRequest } from "../../platform/api/request";
import { ApiProblemError } from "../../platform/api/problem";

function useCustomerResource<T>(key: string, path: `/api/v1/${string}`) {
  const { credential, signOut } = useAuth();
  return useQuery({
    queryKey: ["customer", credential?.subject, key],
    queryFn: async () => {
      if (!credential) throw new Error("Authentication is required.");
      try {
        return await apiRequest<T>(path, { accessToken: credential.accessToken });
      } catch (error) {
        if (error instanceof ApiProblemError && error.problem.status === 401)
          await signOut();
        throw error;
      }
    },
    enabled: Boolean(credential),
    staleTime: 30_000,
    gcTime: 5 * 60_000,
    retry: (failureCount, error) => {
      if (failureCount >= 2) return false;
      return !(
        error instanceof ApiProblemError &&
        [401, 403, 409, 412].includes(error.problem.status)
      );
    },
  });
}

export const useCustomerProfile = () =>
  useCustomerResource<CustomerProfile>("profile", customerResourcePaths.profile);
export const useCustomerSessions = () =>
  useCustomerResource<CustomerSessions>("sessions", customerResourcePaths.sessions);
export const useCustomerConsents = () =>
  useCustomerResource<CustomerConsents>("consents", customerResourcePaths.consents);
export const useCustomerGarage = () =>
  useCustomerResource<CustomerGarage>("garage", customerResourcePaths.garage);
export const useCustomerSecurity = () =>
  useCustomerResource<CustomerSecurity>("security", customerResourcePaths.security);
export const useCustomerDataRequests = () =>
  useCustomerResource<CustomerDataRequests>("data-requests", customerResourcePaths.dataRequests);
export const useVehicleModels = () =>
  useCustomerResource<VehicleModels>("vehicle-models", customerResourcePaths.models);
