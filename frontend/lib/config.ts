/**
 * Configuration for API endpoints
 * Supports both development and production environments
 */

export const API_CONFIG = {
  // In development: use localhost
  // In production: use environment variable
  BASE_URL: process.env.NODE_ENV === 'production' 
    ? (process.env.NEXT_PUBLIC_API_URL || 'https://your-api-domain.com')
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
