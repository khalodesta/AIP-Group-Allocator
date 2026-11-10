import type { NextConfig } from "next";
const portableWindows = process.env.PORTABLE_WINDOWS_BUILD === "1";
const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: "standalone",
  // The CP-SAT budget can be 120s, followed by BUS/reflection/hotel solves.
  // Next's default 30s proxy timeout aborts valid allocation requests with 500.
  experimental: { proxyTimeout: 180_000 },
  async rewrites() {
    return portableWindows
      ? [{ source: "/api/:path*", destination: "http://127.0.0.1:8000/api/:path*" }]
      : [];
  },
};
export default nextConfig;
