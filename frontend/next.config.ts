import type { NextConfig } from "next";

// On Vercel the /api rewrite lives in vercel.json and points at the FastAPI service, so
// API_ORIGIN is unset there and this adds nothing. Locally the two run as separate
// processes and whichever server is running proxies to the backend, which keeps cookies
// and the OAuth callback on one origin in every environment.
const API_ORIGIN =
  process.env.API_ORIGIN ??
  (process.env.NODE_ENV === "development" ? "http://127.0.0.1:8000" : null);

const nextConfig: NextConfig = {
  // Next 16 refuses dev assets to origins it was not started for, so reaching the dev
  // server by IP — from another device on the network, or from a headless browser —
  // otherwise returns 403 for every chunk and nothing hydrates.
  allowedDevOrigins: ["localhost", "127.0.0.1"],

  images: {
    // GitHub serves every avatar from this one host.
    remotePatterns: [{ protocol: "https", hostname: "avatars.githubusercontent.com" }],
  },

  rewrites() {
    return API_ORIGIN ? [{ source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` }] : [];
  },
};

export default nextConfig;
