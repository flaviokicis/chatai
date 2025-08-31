/**
 * Configuration for API endpoints
 * Supports both development and production environments
 */

export const API_CONFIG = {
  // Development: Frontend (3000) calls Backend (8080) directly
  // Production: Same server serves both, use relative paths
  BASE_URL: process.env.NODE_ENV === 'production' 
    ? '' // Empty string for relative paths when served from Python
    : 'http://localhost:8080',
    
  ENDPOINTS: {
    CONTROLLER: '/api/controller',
  }
} as const;

export const getApiUrl = (endpoint: string) => {
  return `${API_CONFIG.BASE_URL}${endpoint}`;
};

// Helper for controller endpoints
export const getControllerUrl = (path: string) => {
  return getApiUrl(`${API_CONFIG.ENDPOINTS.CONTROLLER}${path}`);
};
