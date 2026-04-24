'use client'

import Link from 'next/link'
import { usePageTitle } from '@/hooks/usePageTitle'
import { Card, SeoShell, buttonStyle } from './_components/SeoShell'
import { HowToUsePanel } from './_components/HowToUsePanel'

export default function SeoOverviewPage({ params }: { params: { projectId: string } }) {
  const { projectId } = params
  usePageTitle('SEO', projectId)
  return (
    <SeoShell
      projectId={projectId}
      title="SEO модуль"
      subtitle="Путь от запросов категории до сохраненного набора релевантных запросов и research-preview генерации."
    >
      <div style={{ display: 'grid', gap: 16 }}>
        <HowToUsePanel projectId={projectId} />
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 16 }}>
          <Card>
            <h2 style={{ marginTop: 0 }}>1. Категории и запросы</h2>
            <p style={{ color: '#64748b' }}>Загрузите CSV в категорию, проверьте готовность и при необходимости очистите корпус.</p>
            <Link href={`/app/project/${projectId}/seo/categories`} style={buttonStyle('primary')}>Открыть категории</Link>
          </Card>
          <Card>
            <h2 style={{ marginTop: 0 }}>2. Анализ товаров</h2>
            <p style={{ color: '#64748b' }}>Найдите товар, запустите анализ карточки, отзывов и фото, затем переходите к подбору запросов.</p>
            <Link href={`/app/project/${projectId}/seo/products`} style={buttonStyle('primary')}>Открыть товары</Link>
          </Card>
          <Card>
            <h2 style={{ marginTop: 0 }}>3. Eval категории 812</h2>
            <p style={{ color: '#64748b' }}>Единственный официальный писатель <code>eligibility_tier</code>. Запускайте здесь, чтобы открывать promote-gates.</p>
            <Link href={`/app/project/${projectId}/seo/categories/812/eval`} style={buttonStyle('primary')}>Открыть Eval 812</Link>
          </Card>
          <Card>
            <h2 style={{ marginTop: 0 }}>4. Research preview генерация</h2>
            <p style={{ color: '#64748b' }}>Генерация живёт только как <strong>preview</strong>. Publish в WB из UI нет и не появится в этой итерации.</p>
            <span style={buttonStyle('ghost')}>Открывается со страницы товара</span>
          </Card>
        </div>
      </div>
    </SeoShell>
  )
}
