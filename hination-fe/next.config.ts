import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emit a self-contained server bundle (.next/standalone) for a lean production image.
  output: "standalone",
  // Keep the native SQLite addon out of the bundler; load it from node_modules at runtime.
  serverExternalPackages: ["better-sqlite3"],
};

export default nextConfig;
