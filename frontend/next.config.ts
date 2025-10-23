import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Client-side SPA served from Python (like old React days)
  // No static export - regular Next.js build for SPA behavior
  
  // Disable image optimization since we're serving from Python
  images: {
    unoptimized: true,
  },
  
  // Disable ESLint during builds for clean CI/CD
  eslint: {
    ignoreDuringBuilds: true,
  },
  
  // Disable TypeScript checking during builds for clean CI/CD
  typescript: {
    ignoreBuildErrors: true,
  },
  
  // STABILITY FIX: Basic Turbopack configuration
  turbopack: {
    rules: {},
  },
  
  // Additional stability settings
  experimental: {
    // Disable some features that can cause instability
    optimizePackageImports: [],
    // Reduce memory pressure
    webpackMemoryOptimizations: true,
  },
  
  // Ensure clean builds by disabling some caching
  onDemandEntries: {
    // Reduce memory pressure
    maxInactiveAge: 25 * 1000,
    pagesBufferLength: 2,
  },
  
  // Proxy API requests to backend during development
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://localhost:8080/api/:path*',
      },
    ];
  },
};

export default nextConfig;
