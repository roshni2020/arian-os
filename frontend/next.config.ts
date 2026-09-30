import type { NextConfig } from "next";

// /api is handled by src/app/api/[...path]/route.ts (recorded sessions + proxy to BACKEND_URL).
const nextConfig: NextConfig = {
  distDir: process.env.NEXT_DIST_DIR || ".next",
};

export default nextConfig;
