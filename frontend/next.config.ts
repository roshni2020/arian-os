import type { NextConfig } from "next";

// Benchmarks, projects and the assistant go to the Python backend at BACKEND_URL.
// Sessions are served from the recorded replays in src/app/api/[...path] unless LIVE_SESSIONS=1
// (a fresh hosted backend has an empty database and no training data).
const backend = process.env.BACKEND_URL;
const proxied = process.env.LIVE_SESSIONS === "1" ? [":path*"] : ["benchmarks/:path*", "projects/:path*", "assistant/:path*", "benchmarks", "projects"];

const nextConfig: NextConfig = {
  distDir: process.env.NEXT_DIST_DIR || ".next",
  async rewrites() {
    return backend ? proxied.map((p) => ({ source: `/api/${p}`, destination: `${backend}/api/${p}` })) : [];
  },
};

export default nextConfig;
