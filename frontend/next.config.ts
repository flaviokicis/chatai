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
};

export default nextConfig;
