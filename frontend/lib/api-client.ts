/**
 * API Client for ChatAI Backend
 * Provides type-safe methods for interacting with the backend API
 */

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8080';

// Types based on the API documentation
export interface Tenant {
  id: string; // UUIDv7
  first_name: string;
  last_name: string;
  email: string;
}

export interface TenantProjectConfig {
  project_description?: string;
  target_audience?: string;
  communication_style?: string;
}

export interface TenantWithConfig extends Tenant {
  project_description?: string;
  target_audience?: string;
  communication_style?: string;
}

export interface UpdateTenantConfigRequest {
  project_description?: string;
  target_audience?: string;
  communication_style?: string;
}

export interface CreateTenantRequest {
  first_name: string;
  last_name: string;
  email: string;
  project_description?: string;
  target_audience?: string;
  communication_style?: string;
}

export interface ChannelInstance {
  id: string; // UUIDv7
  channel_type: string;
  identifier: string;
  phone_number?: string;
}

export interface CreateChannelRequest {
  channel_type: string;
  identifier: string;
  phone_number?: string;
  extra?: Record<string, unknown>;
}

export interface Flow {
  id: string; // UUIDv7
  name: string;
  flow_id: string;
  channel_instance_id: string; // UUIDv7
  definition?: Record<string, unknown>;
  is_active: boolean;
}

export interface CreateFlowRequest {
  name: string;
  flow_id: string;
  channel_instance_id: string; // UUIDv7
  definition: Record<string, unknown>;
}

export interface UpdateFlowRequest {
  name?: string;
  definition?: Record<string, unknown>;
  is_active?: boolean;
}

export interface ChannelWithFlows {
  id: string; // UUIDv7
  channel_type: string;
  identifier: string;
  phone_number?: string;
  flows: Flow[];
}

export interface UpdateChannelFlowRequest {
  flow_id: string; // UUIDv7
}

export interface Contact {
  id: string; // UUIDv7
  external_id: string;
  display_name?: string;
  phone_number?: string;
  created_at: string;
  consent_opt_in_at?: string;
  consent_revoked_at?: string;
}

export interface Message {
  id: string; // UUIDv7
  direction: 'inbound' | 'outbound';
  status: string;
  text: string;
  created_at: string;
  sent_at?: string;
  delivered_at?: string;
  read_at?: string;
  provider_message_id?: string;
}

export interface FlowChatMessage {
  id: string; // UUIDv7
  role: 'user' | 'assistant' | 'system';
  content: string;
  created_at: string;
}

export interface FlowChatResponse {
  messages: FlowChatMessage[];
  flow_was_modified: boolean;
  modification_summary?: string;
}

export interface FlowVersion {
  id: string; // UUIDv7
  version_number: number;
  change_description?: string;
  created_at: string;
  created_by?: string;
}

export interface ChatThread {
  id: string; // UUIDv7
  status: 'open' | 'closed' | 'archived';
  subject?: string;
  last_message_at: string;
  created_at: string;
  contact: Contact;
  messages?: Message[];
}

class APIError extends Error {
  constructor(
    public status: number,
    public statusText: string,
    public data: unknown
  ) {
    super(`API Error ${status}: ${statusText}`);
  }
}

async function apiRequest<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = `${BASE_URL}${endpoint}`;
  
  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  });

  let data;
  try {
    data = await response.json();
  } catch {
    // Response might not be JSON
    data = null;
  }

  if (!response.ok) {
    throw new APIError(response.status, response.statusText, data);
  }

  return data;
}

// Default tenant handling: try env var -> localStorage -> fallback to first tenant from API
let DEFAULT_TENANT_ID: string | null = process.env.NEXT_PUBLIC_DEMO_TENANT_ID || null;
if (!DEFAULT_TENANT_ID && typeof window !== 'undefined') {
  DEFAULT_TENANT_ID = window.localStorage.getItem('tenant_id');
}

async function getOrInitDefaultTenantId(): Promise<string> {
  if (DEFAULT_TENANT_ID) return DEFAULT_TENANT_ID;
  const tenants = await apiRequest<Tenant[]>(`/api/tenants`);
  if (Array.isArray(tenants) && tenants.length > 0) {
    DEFAULT_TENANT_ID = tenants[0].id;
    if (typeof window !== 'undefined') {
      window.localStorage.setItem('tenant_id', DEFAULT_TENANT_ID);
    }
    return DEFAULT_TENANT_ID;
  }
  // Create a demo tenant if none exists (dev convenience)
  const demo = await apiRequest<Tenant>(`/api/tenants`, {
    method: 'POST',
    body: JSON.stringify({
      first_name: 'Demo',
      last_name: 'User',
      email: 'demo@example.com',
    } as CreateTenantRequest),
  });
  DEFAULT_TENANT_ID = demo.id;
  if (typeof window !== 'undefined') {
    window.localStorage.setItem('tenant_id', DEFAULT_TENANT_ID);
  }
  return DEFAULT_TENANT_ID;
}

export const api = {
  // Tenant endpoints
  tenants: {
    list: (): Promise<Tenant[]> => 
      apiRequest('/api/controller/tenants'),
    
    create: (tenant: CreateTenantRequest): Promise<Tenant> => 
      apiRequest('/api/controller/tenants', {
        method: 'POST',
        body: JSON.stringify(tenant),
      }),
    
    get: async (tenantId?: string): Promise<TenantWithConfig> => {
      const id = tenantId || (await getOrInitDefaultTenantId());
      return apiRequest(`/api/controller/tenants/${id}`);
    },
    
    updateConfig: async (
      tenantId: string | undefined, 
      config: UpdateTenantConfigRequest
    ): Promise<TenantWithConfig> => {
      const id = tenantId || (await getOrInitDefaultTenantId());
      return apiRequest(`/api/controller/tenants/${id}/config`, {
        method: 'PATCH',
        body: JSON.stringify(config),
      });
    },
  },

  // Channel endpoints (user-accessible, no admin auth required)
  channels: {
    list: async (tenantId?: string): Promise<ChannelInstance[]> => {
      const id = tenantId || (await getOrInitDefaultTenantId());
      return apiRequest(`/api/channels/tenant/${id}`);
    },
  },

  // Flow endpoints (public, no auth required)
  flows: {
    list: async (tenantId?: string): Promise<Flow[]> => {
      const id = tenantId || (await getOrInitDefaultTenantId());
      return apiRequest(`/api/tenants/${id}/flows`);
    },
    
    create: async (tenantId: string | undefined, flow: CreateFlowRequest): Promise<Flow> => {
      const id = tenantId || (await getOrInitDefaultTenantId());
      return apiRequest(`/api/tenants/${id}/flows`, {
        method: 'POST',
        body: JSON.stringify(flow),
      });
    },
    
    update: async (tenantId: string | undefined, flowId: string, flow: UpdateFlowRequest): Promise<Flow> => {
      const id = tenantId || (await getOrInitDefaultTenantId());
      return apiRequest(`/api/tenants/${id}/flows/${flowId}`, {
        method: 'PUT',
        body: JSON.stringify(flow),
      });
    },
    
    getExample: (): Promise<Record<string, unknown>> => 
      apiRequest('/api/flows/example/raw'),
    
    getExampleCompiled: (): Promise<Record<string, unknown>> =>
      apiRequest('/api/flows/example/compiled'),
    
    getCompiled: (flowId: string): Promise<Record<string, unknown>> =>
      apiRequest(`/api/flows/${flowId}/compiled`),
    
    // Version history endpoints
    getVersions: (flowId: string): Promise<FlowVersion[]> =>
      apiRequest(`/api/flows/${flowId}/versions`),
    
    restoreVersion: (flowId: string, versionNumber: number): Promise<{ message: string; current_version: number }> =>
      apiRequest(`/api/flows/${flowId}/restore`, {
        method: 'POST',
        body: JSON.stringify({ version_number: versionNumber }),
      }),
  },

  flowChat: {
    send: (
      flowId: string, 
      content: string,
      options?: {
        simplified_view_enabled?: boolean;
        active_path?: string | null;
      }
    ): Promise<FlowChatResponse> =>
      apiRequest(`/api/flows/${flowId}/chat/send`, {
        method: 'POST',
        body: JSON.stringify({ 
          content,
          simplified_view_enabled: options?.simplified_view_enabled || false,
          active_path: options?.active_path || null
        }),
      }),

    list: (flowId: string): Promise<FlowChatMessage[]> =>
      apiRequest(`/api/flows/${flowId}/chat/messages`),

    receive: (flowId: string): Promise<FlowChatMessage | null> =>
      apiRequest(`/api/flows/${flowId}/chat/receive`),

    clear: (flowId: string): Promise<{ message: string }> =>
      apiRequest(`/api/flows/${flowId}/chat/clear`, {
        method: 'POST',
      }),
  },

  // Chat endpoints
  chats: {
    listThreads: async (tenantId?: string, params?: {
      channel_instance_id?: string;
      limit?: number;
      offset?: number;
    }): Promise<ChatThread[]> => {
      const id = tenantId || (await getOrInitDefaultTenantId());
      const searchParams = new URLSearchParams();
      if (params?.channel_instance_id) searchParams.set('channel_instance_id', params.channel_instance_id);
      if (params?.limit) searchParams.set('limit', params.limit.toString());
      if (params?.offset) searchParams.set('offset', params.offset.toString());
      
      const query = searchParams.toString();
      return apiRequest(`/api/chats/tenants/${id}/threads${query ? `?${query}` : ''}`);
    },
    
    getThread: async (tenantId: string | undefined, threadId: string): Promise<ChatThread> => {
      const id = tenantId || (await getOrInitDefaultTenantId());
      return apiRequest(`/api/chats/tenants/${id}/threads/${threadId}`);
    },
    
    listContacts: async (tenantId?: string, params?: {
      limit?: number;
      offset?: number;
    }): Promise<Contact[]> => {
      const id = tenantId || (await getOrInitDefaultTenantId());
      const searchParams = new URLSearchParams();
      if (params?.limit) searchParams.set('limit', params.limit.toString());
      if (params?.offset) searchParams.set('offset', params.offset.toString());
      
      const query = searchParams.toString();
      return apiRequest(`/api/chats/tenants/${id}/contacts${query ? `?${query}` : ''}`);
    },
  },

  // System endpoints
  health: (): Promise<string> => 
    apiRequest('/health'),

  // Admin endpoints (for managing channels and flows)
  admin: {
    listChannels: async (tenantId?: string): Promise<ChannelInstance[]> => {
      const id = tenantId || (await getOrInitDefaultTenantId());
      return apiRequest(`/api/controller/tenants/${id}/channels`);
    },
    
    getChannelWithFlows: async (channelId: string, tenantId?: string): Promise<ChannelWithFlows> => {
      const id = tenantId || (await getOrInitDefaultTenantId());
      return apiRequest(`/api/controller/tenants/${id}/channels/${channelId}`);
    },
    
    setChannelActiveFlow: async (channelId: string, request: UpdateChannelFlowRequest, tenantId?: string): Promise<{ message: string }> => {
      const id = tenantId || (await getOrInitDefaultTenantId());
      return apiRequest(`/api/controller/tenants/${id}/channels/${channelId}/active-flow`, {
        method: 'PATCH',
        body: JSON.stringify(request),
      });
    },
    
    listFlows: async (tenantId?: string): Promise<Flow[]> => {
      const id = tenantId || (await getOrInitDefaultTenantId());
      return apiRequest(`/api/controller/tenants/${id}/flows`);
    },

    // Admin phone management
    getAdminPhones: async (tenantId?: string): Promise<{ admin_phone_numbers: string[] }> => {
      const id = tenantId || (await getOrInitDefaultTenantId());
      return apiRequest(`/api/tenants/${id}/admin-phones`);
    },

    updateAdminPhones: async (adminPhones: string[], tenantId?: string): Promise<{ admin_phone_numbers: string[] }> => {
      const id = tenantId || (await getOrInitDefaultTenantId());
      return apiRequest(`/api/tenants/${id}/admin-phones`, {
        method: 'PUT',
        body: JSON.stringify({ admin_phone_numbers: adminPhones }),
      });
    },
  },
};

export { DEFAULT_TENANT_ID };
export { getOrInitDefaultTenantId };
