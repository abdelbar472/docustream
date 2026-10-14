import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  async headers() {
    // Never let browsers cache the HTML shell: it references hashed asset
    // filenames, so a stale copy breaks styling after every rebuild.
    return [
      {
        source: "/:path((?!_next/static|_next/image|favicon.ico).*)",
        headers: [{ key: "Cache-Control", value: "no-store, must-revalidate" }],
      },
    ];
  },
};

export default nextConfig;
