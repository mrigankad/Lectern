import path from "node:path";
import type { NextConfig } from "next";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const MOCK = process.env.LECTERN_MOCK === "1";

const nextConfig: NextConfig = {
  // This folder is the project root (there may be other lockfiles higher up on the machine).
  outputFileTracingRoot: path.join(__dirname),
  devIndicators: false,
  async rewrites() {
    return [
      MOCK
        ? // Development only: `pnpm dev:mock` serves the spec from src/mock.
          { source: "/api/:path*", destination: "/mock-api/:path*" }
        : { source: "/api/:path*", destination: `${API_URL}/api/:path*` },
    ];
  },
};

export default nextConfig;
