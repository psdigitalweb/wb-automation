import type { Metadata } from 'next'
import { headers } from 'next/headers'

function getApiBase(): string {
  const base = process.env.NEXT_PUBLIC_API_URL || process.env.API_PROXY_TARGET || 'http://api:8000'
  return base.endsWith('/api') ? base : base.replace(/\/+$/, '') + '/api'
}

async function fetchProjectName(projectId: string): Promise<string | null> {
  try {
    const apiBase = getApiBase()
    const headersList = await headers()
    const auth = headersList.get('authorization')
    const cookie = headersList.get('cookie')
    const res = await fetch(`${apiBase}/v1/projects/${projectId}`, {
      cache: 'no-store',
      headers: {
        ...(auth && { Authorization: auth }),
        ...(cookie && { Cookie: cookie }),
      },
    })
    if (!res.ok) return null
    const project = await res.json()
    return project?.name ?? null
  } catch {
    return null
  }
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ projectId: string }>
}): Promise<Metadata> {
  const { projectId } = await params
  const projectName = await fetchProjectName(projectId)
  const title = projectName
    ? `Финансовые отчёты Wildberries — ${projectName}`
    : `Финансовые отчёты Wildberries — #${projectId}`
  return { title }
}

export default function ReportsLayout({ children }: { children: React.ReactNode }) {
  return children
}
