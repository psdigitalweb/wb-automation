import { NextResponse } from 'next/server'

type Ctx = { params: { path?: string[] } }

export const runtime = 'nodejs'

function getBackendCandidates() {
  const baseFromEnv =
    process.env.NEXT_PUBLIC_API_URL || process.env.API_PROXY_TARGET || 'http://localhost:8000/api'

  // Normalize: base must end with "/api"
  const normalized = baseFromEnv.endsWith('/api') ? baseFromEnv : baseFromEnv.replace(/\/+$/, '') + '/api'

  // Candidate 1: env-provided (docker: http://api:8000/api)
  // Candidate 2: host fallback (http://localhost:8000/api)
  // Candidate 3: docker service name fallback (if env isn't set)
  const candidates = [normalized, 'http://api:8000/api', 'http://localhost:8000/api']
  return Array.from(new Set(candidates))
}

async function proxy(req: Request, ctx: Ctx) {
  const path = (ctx.params.path || []).join('/')
  const url = new URL(req.url)
  const search = url.search

  const candidates = getBackendCandidates()
  const targetUrls = candidates.map((base) => `${base}/v1/${path}${search}`)

  // Forward a minimal safe set of headers. Authorization is required for most endpoints.
  const headers = new Headers()
  const auth = req.headers.get('authorization')
  if (auth) headers.set('authorization', auth)
  const cookie = req.headers.get('cookie')
  if (cookie) headers.set('cookie', cookie)
  const contentType = req.headers.get('content-type')
  if (contentType) headers.set('content-type', contentType)

  const method = req.method.toUpperCase()
  const hasBody = !['GET', 'HEAD'].includes(method)
  const body = hasBody ? await req.arrayBuffer() : undefined

  let lastErr: any = null

  for (const targetUrl of targetUrls) {
    try {
      const upstream = await fetch(targetUrl, {
        method,
        headers,
        body,
        // Avoid caching on proxy layer
        cache: 'no-store',
      })

      const respHeaders = new Headers()
      const passThrough = ['content-type', 'cache-control', 'etag', 'location']
      for (const h of passThrough) {
        const v = upstream.headers.get(h)
        if (v) respHeaders.set(h, v)
      }

      const getSetCookie = (upstream.headers as any)?.getSetCookie as undefined | (() => string[])
      const setCookies = getSetCookie ? getSetCookie.call(upstream.headers) : []
      if (Array.isArray(setCookies) && setCookies.length) {
        for (const c of setCookies) respHeaders.append('set-cookie', c)
      } else {
        const sc = upstream.headers.get('set-cookie')
        if (sc) respHeaders.append('set-cookie', sc)
      }

      respHeaders.set('x-ecomcore-proxy', '1')
      respHeaders.set('x-ecomcore-proxy-target', targetUrl)
      respHeaders.set(
        'x-ecomcore-set-cookie',
        (Array.isArray(setCookies) && setCookies.length) || upstream.headers.get('set-cookie') ? '1' : '0'
      )

      const raw = await upstream.arrayBuffer()
      return new NextResponse(raw, { status: upstream.status, headers: respHeaders })
    } catch (e: any) {
      lastErr = e
      continue
    }
  }

  return NextResponse.json(
    {
      detail: 'API proxy failed',
      tried: targetUrls,
      error: lastErr?.message || String(lastErr),
    },
    { status: 502, headers: { 'x-ecomcore-proxy': '1', 'x-ecomcore-set-cookie': '0' } }
  )
}

export const GET = proxy
export const POST = proxy
export const PUT = proxy
export const PATCH = proxy
export const DELETE = proxy
