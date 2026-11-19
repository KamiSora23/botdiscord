import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const API_URL = process.env.NEXUS_API_URL ?? "http://127.0.0.1:8000";

// Content-Security-Policy: solo scripts y conexiones del propio dominio. Las imágenes pueden ser
// cualquier https (avatares de Discord e imágenes que el usuario pone en sus embeds).
// Next.js necesita 'unsafe-inline' para sus scripts de hidratación y 'unsafe-eval' solo en desarrollo.
const isDev = process.env.NODE_ENV !== "production";
const CSP = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob: https:",
  "font-src 'self' data:",
  `connect-src 'self'${isDev ? " ws: http://localhost:* http://127.0.0.1:*" : ""}`,
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join("; ");

const nextConfig: NextConfig = {
  poweredByHeader: false,
  output: "standalone", // imagen Docker pequeña (fase 9)
  // El navegador solo habla con localhost:3000; /api/* se reenvía a FastAPI (mismo origen, sin CORS).
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Content-Security-Policy", value: CSP },
        ],
      },
    ];
  },
  images: {
    remotePatterns: [{ protocol: "https", hostname: "cdn.discordapp.com" }],
  },
};

export default createNextIntlPlugin("./i18n/request.ts")(nextConfig);
