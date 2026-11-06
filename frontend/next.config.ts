import type { NextConfig } from "next";
const portableWindows = process.env.PORTABLE_WINDOWS_BUILD === "1";
const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: "standalone",
  async rewrites() {
    return portableWindows
      ? [{ source: "/api/:path*", destination: "http://127.0.0.1:8000/api/:path*" }]
      : [];
  },
};
export default nextConfig;
