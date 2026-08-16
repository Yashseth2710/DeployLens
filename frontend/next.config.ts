import type { NextConfig } from "next";

const API_ORIGIN = process.env.API_ORIGIN ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // On Vercel the /api rewrite lives in vercel.json and points at the FastAPI service.
  // Locally the two run as separate processes, so the dev server proxies instead —
  // that keeps cookies and the OAuth callback on a single origin either way.
  rewrites() {
    if (process.env.NODE_ENV === "production") {
      return [];
    }
    return [{ source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` }];
  },
};

export default nextConfig;
