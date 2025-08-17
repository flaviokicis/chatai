"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { 
  api, 
  DEFAULT_TENANT_ID, 
  type CreateTenantRequest, 
  type CreateFlowRequest, 
  type UpdateTenantConfigRequest 
} from "../api-client";

// Query Keys
export const queryKeys = {
  tenants: ['tenants'] as const,
  tenant: (id: string | null | undefined) => ['tenants', id] as const,
  channels: (tenantId: string | null | undefined) => ['channels', tenantId] as const,
  flows: (tenantId: string | null | undefined) => ['flows', tenantId] as const,
  chatThreads: (tenantId: string | null | undefined, params?: any) => ['chatThreads', tenantId, params] as const,
  contacts: (tenantId: string | null | undefined, params?: any) => ['contacts', tenantId, params] as const,
  exampleFlow: ['exampleFlow'] as const,
} as const;

// Tenant hooks
export function useTenants() {
  return useQuery({
    queryKey: queryKeys.tenants,
    queryFn: api.tenants.list,
  });
}

export function useTenant(tenantId: string | null | undefined = DEFAULT_TENANT_ID) {
  return useQuery({
    queryKey: queryKeys.tenant(tenantId),
    queryFn: () => api.tenants.get(tenantId ?? undefined),
    retry: false, // Don't retry if tenant doesn't exist
  });
}

export function useCreateTenant() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: api.tenants.create,
    onSuccess: () => {
      // Invalidate tenants list to refetch
      queryClient.invalidateQueries({ queryKey: queryKeys.tenants });
    },
  });
}

export function useUpdateTenantConfig() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: ({ tenantId = DEFAULT_TENANT_ID, ...config }: UpdateTenantConfigRequest & { tenantId?: string | null }) =>
      api.tenants.updateConfig(tenantId ?? undefined, config),
    onSuccess: (_, variables) => {
      // Invalidate specific tenant and tenants list
      const tenantId = variables.tenantId || DEFAULT_TENANT_ID;
      queryClient.invalidateQueries({ queryKey: queryKeys.tenant(tenantId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.tenants });
    },
  });
}

// Channel hooks
export function useChannels(tenantId: string | null | undefined = DEFAULT_TENANT_ID) {
  return useQuery({
    queryKey: queryKeys.channels(tenantId),
    queryFn: () => api.channels.list(tenantId ?? undefined),
  });
}

// Flow hooks
export function useFlows(tenantId: string | null | undefined = DEFAULT_TENANT_ID) {
  return useQuery({
    queryKey: queryKeys.flows(tenantId),
    queryFn: () => api.flows.list(tenantId ?? undefined),
    // Flows change less frequently, cache for longer
    staleTime: 1000 * 60 * 10, // 10 minutes
  });
}

export function useCreateFlow() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: ({ tenantId = DEFAULT_TENANT_ID, ...flow }: CreateFlowRequest & { tenantId?: string | null }) => 
      api.flows.create(tenantId ?? undefined, flow),
    onSuccess: (_, variables) => {
      // Invalidate flows list to refetch
      queryClient.invalidateQueries({ 
        queryKey: queryKeys.flows(variables.tenantId || DEFAULT_TENANT_ID) 
      });
    },
  });
}

export function useExampleFlow() {
  return useQuery({
    queryKey: queryKeys.exampleFlow,
    queryFn: api.flows.getExample,
    // Example flow doesn't change, cache for very long
    staleTime: 1000 * 60 * 60, // 1 hour
  });
}

// Chat hooks
export function useChatThreads(
  tenantId: string | null | undefined = DEFAULT_TENANT_ID, 
  params?: { channel_instance_id?: string; limit?: number; offset?: number }
) {
  return useQuery({
    queryKey: queryKeys.chatThreads(tenantId, params),
    queryFn: () => api.chats.listThreads(tenantId ?? undefined, params),
    // Chat data changes frequently, shorter stale time
    staleTime: 1000 * 60 * 2, // 2 minutes
    // Refetch when window regains focus for chat data
    refetchOnWindowFocus: true,
  });
}

export function useContacts(
  tenantId: string | null | undefined = DEFAULT_TENANT_ID,
  params?: { limit?: number; offset?: number }
) {
  return useQuery({
    queryKey: queryKeys.contacts(tenantId, params),
    queryFn: () => api.chats.listContacts(tenantId ?? undefined, params),
    // Contacts change less frequently
    staleTime: 1000 * 60 * 5, // 5 minutes
  });
}
