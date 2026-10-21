import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  turbopack: {
    root: path.join(__dirname),
  },
  // With API_PROXY_TARGET set (hosted deploys, see docs/DEPLOY.md), the
  // browser calls /api/* on this app's own origin and Next forwards it to
  // the backend. The auth cookie is then first-party, so SameSite=Lax keeps
  // working even when frontend and backend live on different domains.
  async rewrites() {
    const target = process.env.API_PROXY_TARGET;
    return target ? [{ source: "/api/:path*", destination: `${target}/api/:path*` }] : [];
  },
};

export default nextConfig;
