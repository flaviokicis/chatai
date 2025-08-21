/**
 * API Client for ChatAI Backend
 * Provides type-safe methods for interacting with the backend API
 */

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

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
  extra?: Record<string, any>;
}

export interface Flow {
  id: string; // UUIDv7
  name: string;
  flow_id: string;
  channel_instance_id: string; // UUIDv7
  definition?: Record<string, any>;
}

export interface CreateFlowRequest {
  name: string;
  flow_id: string;
  channel_instance_id: string; // UUIDv7
  definition: Record<string, any>;
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
    public data: any
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
  const tenants = await apiRequest<Tenant[]>(`/admin/tenants`);
  if (Array.isArray(tenants) && tenants.length > 0) {
    DEFAULT_TENANT_ID = tenants[0].id;
    if (typeof window !== 'undefined') {
      window.localStorage.setItem('tenant_id', DEFAULT_TENANT_ID);
    }
    return DEFAULT_TENANT_ID;
  }
  // Create a demo tenant if none exists (dev convenience)
  const demo = await apiRequest<Tenant>(`/admin/tenants`, {
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
      apiRequest('/admin/tenants'),
    
    create: (tenant: CreateTenantRequest): Promise<Tenant> => 
      apiRequest('/admin/tenants', {
        method: 'POST',
        body: JSON.stringify(tenant),
      }),
    
    get: async (tenantId?: string): Promise<TenantWithConfig> => {
      const id = tenantId || (await getOrInitDefaultTenantId());
      return apiRequest(`/admin/tenants/${id}`);
    },
    
    updateConfig: async (
      tenantId: string | undefined, 
      config: UpdateTenantConfigRequest
    ): Promise<TenantWithConfig> => {
      const id = tenantId || (await getOrInitDefaultTenantId());
      return apiRequest(`/admin/tenants/${id}/config`, {
        method: 'PATCH',
        body: JSON.stringify(config),
      });
    },
  },

  // Channel endpoints
  channels: {
    list: async (tenantId?: string): Promise<ChannelInstance[]> => {
      const id = tenantId || (await getOrInitDefaultTenantId());
      return apiRequest(`/admin/tenants/${id}/channels`);
    },
    
    create: async (tenantId: string | undefined, channel: CreateChannelRequest): Promise<ChannelInstance> => {
      const id = tenantId || (await getOrInitDefaultTenantId());
      return apiRequest(`/admin/tenants/${id}/channels`, {
        method: 'POST',
        body: JSON.stringify(channel),
      });
    },
  },

  // Flow endpoints
  flows: {
    list: async (tenantId?: string): Promise<Flow[]> => {
      const id = tenantId || (await getOrInitDefaultTenantId());
      return apiRequest(`/admin/tenants/${id}/flows`);
    },
    
    create: async (tenantId: string | undefined, flow: CreateFlowRequest): Promise<Flow> => {
      const id = tenantId || (await getOrInitDefaultTenantId());
      return apiRequest(`/admin/tenants/${id}/flows`, {
        method: 'POST',
        body: JSON.stringify(flow),
      });
    },
    
    getExample: (): Promise<any> => 
      apiRequest('/flows/example/raw'),
    
    getExampleCompiled: (): Promise<any> => 
      apiRequest('/flows/example/compiled'),
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
      return apiRequest(`/chats/tenants/${id}/threads${query ? `?${query}` : ''}`);
    },
    
    getThread: async (tenantId: string | undefined, threadId: string): Promise<ChatThread> => {
      const id = tenantId || (await getOrInitDefaultTenantId());
      return apiRequest(`/chats/tenants/${id}/threads/${threadId}`);
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
      return apiRequest(`/chats/tenants/${id}/contacts${query ? `?${query}` : ''}`);
    },
  },

  // System endpoints
  health: (): Promise<string> => 
    apiRequest('/health'),
};

export { DEFAULT_TENANT_ID };
export { getOrInitDefaultTenantId };
