/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  reactStrictMode: true,
  async redirects() {
    return [
      { source: '/unit-pnl', destination: '/app/project/1/wildberries/finances/unit-pnl', permanent: false },
      { source: '/price-discrepancies', destination: '/app/project/1/wildberries/price-discrepancies?only_below_rrp=true', permanent: false },
    ]
  },
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

