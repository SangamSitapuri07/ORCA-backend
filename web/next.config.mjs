/** @type {import('next').NextConfig} */
const backendUrl = (process.env.ORCA_BACKEND_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

const nextConfig = {
  // Arena preview and local development hosts are accepted by the dev server.
  allowedDevOrigins: ["localhost", "127.0.0.1", "*.e2b.app"],

  // Keep browser requests same-origin. Configure the server-side destination
  // with ORCA_BACKEND_URL in production; the default is local development.
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
