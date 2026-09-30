import type { NextConfig } from "next";

// Unset BACKEND_URL (e.g. a plain Vercel deploy) serves recorded sessions from src/app/api/[...path].
const backend = process.env.BACKEND_URL;

const nextConfig: NextConfig = {
  distDir: process.env.NEXT_DIST_DIR || ".next",
  async rewrites() {
    return backend ? [{ source: "/api/:path*", destination: `${backend}/api/:path*` }] : [];
  },
};

export default nextConfig;
