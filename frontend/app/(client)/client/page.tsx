import { headers } from 'next/headers'
import ClientReportsPage from './ClientReportsPage'

export default async function Page() {
  const headersList = await headers()
  const host = headersList.get('host') || ''
  const hostname = host.split(':')[0].trim().toLowerCase()

  return <ClientReportsPage initialHostname={hostname} />
}
