import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // For now, disable static export due to dynamic routes
  // Enable this when ready for CDN deployment
  // output: 'export',
  
  // Disable image optimization for better performance
  images: {
    unoptimized: true,
  },
  
  // Configure trailing slash behavior
  trailingSlash: true,
  
  // Configure asset prefix for CDN (can be set via env var)
  assetPrefix: process.env.NEXT_PUBLIC_CDN_URL || '',
  
  // Disable ESLint during builds for now
  eslint: {
    ignoreDuringBuilds: true,
  },
  
  // Disable TypeScript checking during builds for now
  typescript: {
    ignoreBuildErrors: true,
  },
};

export default nextConfig;
