import { redirect } from 'next/navigation'

export default function SeoProductQueriesRedirectPage({
  params,
  searchParams,
}: {
  params: { projectId: string; nmId: string }
  searchParams: { category_id?: string }
}) {
  const categoryId = searchParams.category_id
  const query = categoryId ? `?category_id=${encodeURIComponent(categoryId)}` : ''
  redirect(`/app/project/${params.projectId}/seo/products/${params.nmId}${query}#seo-query-selection`)
}
