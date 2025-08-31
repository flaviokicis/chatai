/**
 * Configuration for API endpoints
 * Supports both development and production environments
 */

export const API_CONFIG = {
  // In development: use localhost backend
  // In production: use relative paths (same server serves frontend + API)
  BASE_URL: process.env.NODE_ENV === 'production' 
    ? '' // Empty string for relative paths when served from Python
    : 'http://localhost:8080',
    
  ENDPOINTS: {
    CONTROLLER: '/controller',
  }
} as const;

export const getApiUrl = (endpoint: string) => {
  return `${API_CONFIG.BASE_URL}${endpoint}`;
};

// Helper for controller endpoints
export const getControllerUrl = (path: string) => {
  return getApiUrl(`${API_CONFIG.ENDPOINTS.CONTROLLER}${path}`);
};
