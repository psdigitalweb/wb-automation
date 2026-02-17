import { NextRequest, NextResponse } from 'next/server'

const REPORTS_HOST = 'reports.zakka.ru'

function getHost(req: NextRequest): string {
  const raw = req.headers.get('host') ?? ''
  return raw.replace(/:\d+$/, '')
}

function isAllowedOnReportsHost(pathname: string): boolean {
  if (pathname === '/client' || pathname.startsWith('/client/')) return true
  if (pathname.startsWith('/_next/')) return true
  if (pathname === '/favicon.ico' || pathname === '/robots.txt') return true
  if (pathname.startsWith('/api/client/')) return true
  return false
}

export function middleware(req: NextRequest) {
  const host = getHost(req)
  const pathname = req.nextUrl.pathname

  if (host !== REPORTS_HOST) {
    return NextResponse.next()
  }

  if (isAllowedOnReportsHost(pathname)) {
    return NextResponse.next()
  }

  const accept = req.headers.get('accept') ?? ''
  const wantsHtml = accept.includes('text/html')

  if (wantsHtml) {
    const url = req.nextUrl.clone()
    url.pathname = '/client/404'
    return NextResponse.rewrite(url)
  }

  return NextResponse.json({ detail: 'Not Found' }, { status: 404 })
}

export const config = {
  matcher: [
    '/((?!_next/static|_next/image).*)',
  ],
}
