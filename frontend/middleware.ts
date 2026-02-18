import { NextRequest, NextResponse } from 'next/server'

const REPORTS_HOST = 'reports.zakka.ru'

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
      return NextResponse.redirect(new URL('/unit-pnl', req.url))
    }
    if (pathname === '/unit-pnl') {
      const url = req.nextUrl.clone()
      url.pathname = '/app/project/1/wildberries/finances/unit-pnl'
      return NextResponse.rewrite(url)
    }
    if (pathname === '/reports') {
      const url = req.nextUrl.clone()
      url.pathname = '/app/project/1/wildberries/finances/reports'
      return NextResponse.rewrite(url)
    }
    if (pathname === '/price-discrepancies') {
      const url = req.nextUrl.clone()
      url.pathname = '/app/project/1/wildberries/price-discrepancies'
      url.searchParams.set('only_below_rrp', 'true')
      return NextResponse.rewrite(url)
    }
    if (pathname.startsWith('/app/project/1/wildberries/finances/unit-pnl')) {
      return NextResponse.redirect(new URL('/unit-pnl' + search, req.url))
    }
    if (pathname.startsWith('/app/project/1/wildberries/finances/reports')) {
      return NextResponse.redirect(new URL('/reports' + search, req.url))
    }
    if (pathname.startsWith('/app/project/1/wildberries/price-discrepancies')) {
      return NextResponse.redirect(new URL('/price-discrepancies' + search, req.url))
    }
    return NextResponse.next()
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
