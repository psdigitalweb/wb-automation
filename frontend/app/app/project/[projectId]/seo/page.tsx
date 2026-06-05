'use client'

import { usePageTitle } from '@/hooks/usePageTitle'
import { Panel, SeoShell, seoStyles } from './_components/SeoShell'

const metrics = [
  ['Категорий', '12'],
  ['Готовы к подбору', '8'],
  ['Товаров с vision', '340 / 847'],
  ['Ожидают проверки', '23'],
]

const demoCategories = [
  ['Кружки', '✓ 2 840', '✓ 47', '✓', '120', '98', '45', '12'],
  ['Футболки', '✓ 5 100', '✓ 83', '✓', '310', '280', '190', '8'],
  ['Мягкие игрушки', '✓ 3 200', '✓ 61', '✓', '95', '72', '30', '3'],
  ['Постеры', '✓ 1 200', '✗ —', '✗', '85', '0', '0', '0'],
  ['Бутылки', '✓ 900', '✓ 22', '⌛', '67', '45', '0', '0'],
  ['Посуда', '✗ —', '✗ —', '✗', '170', '0', '0', '0'],
]

export default function SeoOverviewPage({ params }: { params: { projectId: string } }) {
  const { projectId } = params
  usePageTitle('SEO', projectId)

  return (
    <SeoShell
      projectId={projectId}
      title="SEO Дашборд"
      subtitle="Рабочая очередь по категориям, vision и наборам запросов."
    >
      <div className={`${seoStyles.metricGrid} ${seoStyles.dashboardMetricGrid}`}>
        {metrics.map(([label, value]) => (
          <div className={seoStyles.metricCard} key={label}>
            <div className={seoStyles.metricLabel}>{label}</div>
            <div className={seoStyles.metricValue}>{value}</div>
          </div>
        ))}
      </div>

      <Panel
        title="Категории"
        subtitle="Состояние query data, кластеров, prior и очереди проверки."
      >
        <div className={seoStyles.tableWrap}>
          <table className={seoStyles.table}>
            <thead>
              <tr>
                <th>Категория</th>
                <th>Запросы</th>
                <th>Кластеры</th>
                <th>Prior</th>
                <th>Товаров</th>
                <th>С vision</th>
                <th>С подбором</th>
                <th>Ждут проверки</th>
              </tr>
            </thead>
            <tbody>
              {demoCategories.map((row) => (
                <tr key={row[0]} className={seoStyles.clickable}>
                  <td><strong>{row[0]}</strong></td>
                  <td className={seoStyles.num}>{row[1]}</td>
                  <td className={seoStyles.num}>{row[2]}</td>
                  <td className={seoStyles.num}>{row[3]}</td>
                  <td className={seoStyles.num}>{row[4]}</td>
                  <td className={seoStyles.num}>{row[5]}</td>
                  <td className={seoStyles.num}>{row[6]}</td>
                  <td>{Number(row[7]) > 0 ? <span className={`${seoStyles.badge} ${seoStyles.info}`}>{row[7]}</span> : <span className={seoStyles.muted}>0</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </SeoShell>
  )
}
