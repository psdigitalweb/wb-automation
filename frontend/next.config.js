/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  reactStrictMode: true,
  async rewrites() {
    // Dev/prod-safe proxy:
    // - Browser calls http://localhost:3000/api/...
    // - Next server (running in Docker) rewrites to the backend service in the same Docker network.
    // Nginx also proxies /api -> api:8000, so both :80 and :3000 work.
    return [
      {
        source: '/api/:path*',
        destination: 'http://api:8000/api/:path*',
      },
    ]
  },
}

module.exports = nextConfig

