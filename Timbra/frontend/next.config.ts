import type { NextConfig } from "next";

// En desarrollo (npm run dev) el front corre aparte y /api se redirige al backend.
// En producción se exporta estático (npm run build) y lo sirve el propio FastAPI.
const dev = process.env.NODE_ENV === "development";
const api = process.env.API_URL || "http://localhost:8000";

const config: NextConfig = dev
  ? { async rewrites() { return [{ source: "/api/:path*", destination: `${api}/api/:path*` }]; } }
  : { output: "export", trailingSlash: true, distDir: "out", images: { unoptimized: true } };

export default config;
