import { NextRequest, NextResponse } from 'next/server'

const REPORTS_HOST = 'reports.zakka.ru'
const REPORTS_ALLOWED_PAGES = new Set([
  '/',
  '/client',
  '/client/404',
  '/unit-pnl',
  '/price-discrepancies',
  '/favicon.ico',
])

const REPORTS_ALLOWED_API_PREFIXES = [
  '/api/v1/projects/1/marketplaces/wildberries/finances/unit-pnl',
  '/api/v1/projects/1/marketplaces/wildberries/products/subjects',
  '/api/v1/projects/1/marketplaces/wildberries/finances/reports/search',
  '/api/v1/projects/1/wildberries/price-discrepancies',
  '/api/v1/projects/1/wildberries/categories',
]

function isAllowedReportsApi(pathname: string): boolean {
  return REPORTS_ALLOWED_API_PREFIXES.some((prefix) => pathname.startsWith(prefix))
}

function getHost(req: NextRequest): string {
  const raw = req.headers.get('host') ?? ''
  return raw.replace(/:\d+$/, '')
}

export function middleware(req: NextRequest) {
  const host = getHost(req)
  const pathname = req.nextUrl.pathname
  const search = req.nextUrl.search

  // --- reports.zakka.ru ---
  if (host === REPORTS_HOST) {
    if (pathname === '/') {
      return NextResponse.redirect(new URL('/client', req.url))
    }
    if (pathname === '/client') {
      return NextResponse.next()
    }
    if (pathname === '/client/404') {
      return NextResponse.next()
    }
    if (pathname === '/unit-pnl') {
      const url = req.nextUrl.clone()
      url.pathname = '/app/project/1/wildberries/finances/unit-pnl'
      return NextResponse.rewrite(url)
    }
    if (pathname === '/price-discrepancies') {
      const url = req.nextUrl.clone()
      url.pathname = '/app/project/1/wildberries/price-discrepancies'
      if (!url.searchParams.has('only_below_rrp')) {
        url.searchParams.set('only_below_rrp', 'true')
      }
      return NextResponse.rewrite(url)
    }
    if (pathname.startsWith('/app/project/1/wildberries/finances/unit-pnl')) {
      return NextResponse.redirect(new URL('/unit-pnl' + search, req.url))
    }
    if (pathname.startsWith('/app/project/1/wildberries/price-discrepancies')) {
      return NextResponse.redirect(new URL('/price-discrepancies' + search, req.url))
    }
    if (pathname.startsWith('/api/')) {
      if (isAllowedReportsApi(pathname)) {
        return NextResponse.next()
      }
      const url = req.nextUrl.clone()
      url.pathname = '/client/404'
      url.search = ''
      return NextResponse.rewrite(url)
    }
    if (REPORTS_ALLOWED_PAGES.has(pathname)) {
      return NextResponse.next()
    }
    const url = req.nextUrl.clone()
    url.pathname = '/client/404'
    url.search = ''
    return NextResponse.rewrite(url)
  }

  // --- other hosts (ecomcore.ru etc.) ---
  if (pathname === '/unit-pnl') {
    return NextResponse.redirect(new URL('/app/project/1/wildberries/finances/unit-pnl' + search, req.url))
  }
  if (pathname === '/price-discrepancies') {
    return NextResponse.redirect(new URL('/app/project/1/wildberries/price-discrepancies?only_below_rrp=true', req.url))
  }

  return NextResponse.next()
}

export const config = {
  matcher: [
    '/((?!_next/static|_next/image).*)',
  ],
}
