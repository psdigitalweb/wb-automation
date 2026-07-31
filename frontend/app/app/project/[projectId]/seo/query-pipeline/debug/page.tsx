'use client'

import Link from 'next/link'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { Fragment, useDeferredValue, useEffect, useState } from 'react'

import PortalBackButton from '@/components/PortalBackButton'
import WBProductLookupInput from '@/components/WBProductLookupInput'
import { usePageTitle } from '@/hooks/usePageTitle'
import {
  apiGetData,
  getWBProductSubjects,
  type ApiError,
  type WBProductLookupItem,
  type WBProductSubjectItem,
} from '@/lib/apiClient'


type QueryTab = 'queries' | 'clusters' | 'audit' | 'compare' | 'hybrid' | 'profiles' | 'scoring_prep' | 'scoring'
type PruningStatus = 'keep' | 'drop' | 'review'
type BucketFilter = 'all' | 'head' | 'mid' | 'tail'
type IntentFilter = 'all' | 'product' | 'category' | 'informational' | 'garbage' | 'unknown'
type HybridProvenanceFilter = 'all' | 'individual' | 'cluster' | 'rejected' | 'fallback'

interface SeoQueryPipelineDiagnosticsSummary {
  total_queries: number
  keep_count: number
  drop_count: number
  review_count: number
  total_clusters: number
  singleton_clusters: number
}

interface SeoQueryPipelinePagination {
  page: number
  page_size: number
  total_count: number
  total_pages: number
}

interface SeoQueryPipelineQueryItem {
  normalized_query_text: string
  ranking_value_used: string
  bucket: 'head' | 'mid' | 'tail'
  pruning_status: PruningStatus
  intent_type: string
  cluster_key: string | null
  cluster_label_candidate: string | null
}

interface SeoQueryPipelineClusterMemberItem {
  normalized_query_text: string
  bucket: 'head' | 'mid' | 'tail'
  ranking_value_used: string
  intent_type: string
  membership_reason_code: string
}

interface SeoQueryPipelineClusterItem {
  cluster_key: string
  cluster_label_candidate: string
  query_count: number
  head_query_count: number
  mid_query_count: number
  tail_query_count: number
  members: SeoQueryPipelineClusterMemberItem[]
}

interface SeoQueryProfileMarkerItem {
  value: string
  normalized_value: string
  family: string | null
  support_query_count: number
  support_share: number
  weighted_support: number
  evidence_queries: string[]
}

interface SeoQueryProfileMarkerDecisionItem {
  slot: string
  value: string
  normalized_value: string
  family: string | null
  support_query_count: number
  support_ratio: number
  evidence_queries: string[]
  source_kinds: string[]
  selected: boolean
  reason: string
}

interface SeoQueryPipelineDebugResponse {
  project_id: number
  category_id: number
  diagnostics: SeoQueryPipelineDiagnosticsSummary
  audit: SeoQueryPipelineAudit
  compare: SeoQueryPipelineCompare
  hybrid_diagnostics: SeoQueryPipelineHybridDiagnostics
  profiles_diagnostics: SeoQueryPipelineProfilesDiagnostics
  scoring_prep_diagnostics: SeoQueryPipelineScoringPrepDiagnostics
  actual_scoring_diagnostics: SeoQueryPipelineActualScoringDiagnostics
  queries_pagination: SeoQueryPipelinePagination
  clusters_pagination: SeoQueryPipelinePagination
  hybrid_pagination: SeoQueryPipelinePagination
  profiles_pagination: SeoQueryPipelinePagination
  scoring_prep_pagination: SeoQueryPipelinePagination
  actual_scoring_pagination: SeoQueryPipelinePagination
  queries: SeoQueryPipelineQueryItem[]
  clusters: SeoQueryPipelineClusterItem[]
  hybrid: SeoQueryPipelineHybridItem[]
  hybrid_cluster_details: SeoQueryPipelineHybridClusterDetailItem[]
  profiles: SeoQueryPipelineProfileItem[]
  scoring_preparations: SeoQueryPipelineScoringPrepItem[]
  actual_scores: SeoQueryPipelineActualScoringItem[]
}

interface SeoQueryPipelineHybridItem {
  normalized_query_text: string
  ranking_value_used: string
  bucket: 'head' | 'mid' | 'tail'
  cluster_key: string | null
  is_anchor: boolean
  cluster_label_candidate: string | null
  cluster_query_count: number | null
  provenance: 'individual' | 'cluster' | 'rejected' | 'fallback'
  source_anchor_query: string | null
  intent_type: string
  inheritance_reason_code: string
}

interface SeoQueryPipelineHybridClusterMemberItem {
  normalized_query_text: string
  bucket: 'head' | 'mid' | 'tail'
  is_anchor: boolean
  provenance: 'individual' | 'cluster' | 'rejected' | 'fallback'
  source_anchor_query: string | null
  intent_type: string
  inheritance_reason_code: string
}

interface SeoQueryPipelineHybridClusterDetailItem {
  cluster_key: string
  cluster_label_candidate: string
  query_count: number
  anchor_query: string | null
  members: SeoQueryPipelineHybridClusterMemberItem[]
}

interface SeoQueryPipelineHybridClusterIssueItem {
  cluster_key: string
  cluster_label_candidate: string
  query_count: number
  rejected_count: number
  reject_rate: string
  anchor_query: string | null
  issue_reason: string | null
}

interface SeoQueryPipelineHybridDiagnostics {
  total_queries_processed: number
  individual_count: number
  cluster_derived_count: number
  rejected_count: number
  fallback_count: number
  sample_inherited_queries: SeoQueryPipelineHybridItem[]
  sample_rejected_queries: SeoQueryPipelineHybridItem[]
  clusters_without_anchor: SeoQueryPipelineHybridClusterIssueItem[]
  clusters_with_high_reject_rate: SeoQueryPipelineHybridClusterIssueItem[]
  annotations_upserted: number
  versions_created: number
}

interface SeoQueryPipelineProfileItem {
  cluster_key: string
  profile_label_candidate: string
  profile_strength: 'strong' | 'medium' | 'weak' | 'empty'
  profile_confidence: number
  source_cluster_key: string
  source_anchor_query: string | null
  source_query_examples: string[]
  query_count: number
  evidence_query_count: number
  weighted_signal: number
  product_type_markers: SeoQueryProfileMarkerItem[]
  use_case_markers: SeoQueryProfileMarkerItem[]
  attribute_markers: SeoQueryProfileMarkerItem[]
  language_markers: SeoQueryProfileMarkerItem[]
  marker_decisions: SeoQueryProfileMarkerDecisionItem[]
  conflicting_attribute_families: string[]
  quality_flags: string[]
  confidence_factors: Record<string, string | number | boolean>
}

interface SeoQueryPipelineProfilesDiagnostics {
  total_profiles_built: number
  strong_profiles_count: number
  medium_profiles_count: number
  weak_profiles_count: number
  empty_profiles_count: number
  profiles_with_conflicts_count: number
  profiles_with_low_confidence_count: number
  counts_by_marker_type: Record<string, number>
  counts_by_attribute_family: Record<string, number>
  sample_profiles: SeoQueryPipelineProfileItem[]
  top_profiles_by_signal: SeoQueryPipelineProfileItem[]
  profiles_with_conflicting_markers: SeoQueryPipelineProfileItem[]
  profiles_with_low_confidence: SeoQueryPipelineProfileItem[]
}

interface SeoQueryPipelineScoringPrepMarkerItem {
  value: string
  normalized_value: string
  family: string | null
  status: 'matched' | 'missed' | 'conflicting' | 'unknown'
  fields_checked: string[]
  matched_fields: string[]
  conflicting_with: string[]
  evidence: string[]
  reason: string
}

interface SeoQueryPipelineScoringPrepProductTypeMatchItem {
  status: 'matched' | 'not_matched' | 'unknown'
  evidence: string[]
  reason: string
  marker_evaluations: SeoQueryPipelineScoringPrepMarkerItem[]
}

interface SeoQueryPipelineScoringPrepUseCaseMatchItem {
  matched_markers: SeoQueryPipelineScoringPrepMarkerItem[]
  missed_markers: SeoQueryPipelineScoringPrepMarkerItem[]
  unknown_markers: SeoQueryPipelineScoringPrepMarkerItem[]
  reason: string
}

interface SeoQueryPipelineScoringPrepAttributeMatchItem {
  matched_markers: SeoQueryPipelineScoringPrepMarkerItem[]
  missed_markers: SeoQueryPipelineScoringPrepMarkerItem[]
  conflicting_markers: SeoQueryPipelineScoringPrepMarkerItem[]
  unknown_markers: SeoQueryPipelineScoringPrepMarkerItem[]
  reason: string
}

interface SeoQueryPipelineScoringPrepSkuEvidenceSummary {
  title_present: boolean
  attributes_present: boolean
  description_present: boolean
  normalized_evidence_fields_used: string[]
}

interface SeoQueryPipelineScoringPrepFlags {
  weak_profile: boolean
  empty_profile: boolean
  missing_product_type: boolean
  conflicting_profile_markers: boolean
  insufficient_sku_data: boolean
}

interface SeoQueryPipelineScoringPrepItem {
  cluster_key: string
  profile_label_candidate: string
  profile_strength: 'strong' | 'medium' | 'weak' | 'empty'
  profile_confidence: number
  product_type_match: SeoQueryPipelineScoringPrepProductTypeMatchItem
  use_case_match: SeoQueryPipelineScoringPrepUseCaseMatchItem
  attribute_match: SeoQueryPipelineScoringPrepAttributeMatchItem
  sku_evidence_summary: SeoQueryPipelineScoringPrepSkuEvidenceSummary
  preparation_flags: SeoQueryPipelineScoringPrepFlags
  readiness_for_scoring: 'ready' | 'partial' | 'poor'
}

interface SeoQueryPipelineScoringPrepDiagnostics {
  project_id: number
  category_id: number
  nm_id: number
  total_cluster_comparisons: number
  ready_count: number
  partial_count: number
  poor_count: number
  product_type_matched_rate: number
  use_case_matched_rate: number
  attribute_matched_rate: number
  insufficient_sku_data_count: number
  weak_profile_count: number
  missing_product_type_count: number
  sample_preparations: SeoQueryPipelineScoringPrepItem[]
}

interface SeoQueryPipelineActualScoringModifiers {
  profile_strength: 'strong' | 'medium' | 'weak' | 'empty'
  profile_strength_multiplier: number
  readiness_for_scoring: 'ready' | 'partial' | 'poor'
  readiness_multiplier: number
  combined_multiplier: number
}

interface SeoQueryPipelineActualScoringPenalty {
  name: string
  value: number
  reason: string
}

interface SeoQueryPipelineActualScoringItem {
  cluster_key: string
  profile_label_candidate: string
  final_score: number
  base_score: number
  weighted_score: number
  product_type_score: number
  use_case_score: number
  attribute_score: number
  modifiers: SeoQueryPipelineActualScoringModifiers
  penalties: SeoQueryPipelineActualScoringPenalty[]
  penalties_total: number
  readiness_for_scoring: 'ready' | 'partial' | 'poor'
  preparation_flags: SeoQueryPipelineScoringPrepFlags
  ranking_eligible: boolean
  generation_eligible: boolean
  generation_guardrail_reason: string | null
  final_reason: string
}

interface SeoQueryPipelineActualScoringDiagnostics {
  project_id: number
  category_id: number
  nm_id: number
  total_clusters_scored: number
  avg_score: number
  top_score: number
  bottom_score: number
  positive_score_count: number
  neutral_score_count: number
  negative_score_count: number
  positive_score_share: number
  neutral_score_share: number
  negative_score_share: number
  avg_product_type_score: number
  avg_use_case_score: number
  avg_attribute_score: number
  top_clusters: SeoQueryPipelineActualScoringItem[]
  bottom_clusters: SeoQueryPipelineActualScoringItem[]
}

interface SeoQueryPipelineAuditQueryItem {
  normalized_query_text: string
  display_query: string
  ranking_value_used: string
  query_type: 'head' | 'mid' | 'tail'
  intent_type: string
  pruning_status: PruningStatus
  pruning_reason_code: string
  source_presence_key: string
  preparation_flag_reasons: string[]
  issue_reason: string | null
}

interface SeoQueryPipelineAuditClusterItem {
  cluster_key: string
  cluster_label_candidate: string
  top_query_text: string
  query_count: number
  head_query_count: number
  mid_query_count: number
  tail_query_count: number
  top_member_ranking_value_used: string
  member_samples: string[]
  issue_reason: string | null
}

interface SeoQueryPipelineAuditClusterPairItem {
  cluster_key_a: string
  cluster_label_candidate_a: string
  query_count_a: number
  cluster_key_b: string
  cluster_label_candidate_b: string
  query_count_b: number
  similarity_score: string
  similarity_basis: string
}

interface SeoQueryPipelineLexicalTighteningMetrics {
  total_clusters: number
  singleton_clusters: number
  two_member_clusters: number
  biggest_cluster_size: number
  suspicious_keep_count: number
}

interface SeoQueryPipelineLexicalImprovedQueryCase {
  normalized_query_text: string
  ranking_value_used: string
  legacy_cluster_label_candidate: string
  legacy_cluster_query_count: number
  tightened_cluster_label_candidate: string
  tightened_cluster_query_count: number
}

interface SeoQueryPipelineLexicalTighteningAudit {
  legacy_metrics: SeoQueryPipelineLexicalTighteningMetrics
  tightened_metrics: SeoQueryPipelineLexicalTighteningMetrics
  legacy_top_biggest_clusters: SeoQueryPipelineAuditClusterItem[]
  tightened_top_biggest_clusters: SeoQueryPipelineAuditClusterItem[]
  legacy_top_near_duplicate_clusters: SeoQueryPipelineAuditClusterPairItem[]
  tightened_top_near_duplicate_clusters: SeoQueryPipelineAuditClusterPairItem[]
  improved_query_cases: SeoQueryPipelineLexicalImprovedQueryCase[]
}

interface SeoQueryPipelineAudit {
  counts_by_pruning_reason_code: Record<string, number>
  query_distribution_by_intent_type: Record<string, number>
  query_distribution_by_bucket: Record<string, number>
  query_distribution_by_intent_and_bucket: Record<string, Record<string, number>>
  kept_flag_counts: Record<string, number>
  suspicious_kept_issue_counts: Record<string, number>
  kept_with_navigation_flag_count: number
  kept_with_informational_flag_count: number
  kept_with_garbage_flag_count: number
  top_suspicious_kept_queries: SeoQueryPipelineAuditQueryItem[]
  top_review_queries: SeoQueryPipelineAuditQueryItem[]
  cluster_size_distribution: Record<string, number>
  two_member_cluster_count: number
  top_biggest_clusters: SeoQueryPipelineAuditClusterItem[]
  top_singleton_clusters_by_ranking: SeoQueryPipelineAuditClusterItem[]
  top_small_high_ranking_clusters: SeoQueryPipelineAuditClusterItem[]
  top_generic_label_clusters: SeoQueryPipelineAuditClusterItem[]
  top_near_duplicate_clusters: SeoQueryPipelineAuditClusterPairItem[]
  lexical_tightening?: SeoQueryPipelineLexicalTighteningAudit | null
}

interface SeoQueryPipelineCompareClusterMemberItem {
  normalized_query_text: string
  display_query: string
  query_type: 'head' | 'mid' | 'tail'
  intent_type: string
  ranking_value_used: string
  assignment_reason_code: string
}

interface SeoQueryPipelineCompareClusterItem {
  project_id: number
  category_id: number
  cluster_key: string
  cluster_label_candidate: string
  top_query_text: string
  query_count: number
  head_query_count: number
  mid_query_count: number
  tail_query_count: number
  semantic_kind: string
  member_samples: string[]
  members: SeoQueryPipelineCompareClusterMemberItem[]
}

interface SeoQueryPipelineCompareGroupItem {
  cluster_key: string
  cluster_label_candidate: string
  query_count: number
  sample_queries: string[]
}

interface SeoQueryPipelineSemanticOverbroadCase {
  semantic_cluster_key: string
  semantic_cluster_label_candidate: string
  semantic_query_count: number
  lexical_group_count: number
  dominant_lexical_group_share: string
  lexical_groups: SeoQueryPipelineCompareGroupItem[]
  sample_queries: string[]
}

interface SeoQueryPipelineSemanticGroupingCase {
  semantic_cluster_key: string
  semantic_cluster_label_candidate: string
  semantic_query_count: number
  lexical_group_count: number
  lexical_groups: SeoQueryPipelineCompareGroupItem[]
  sample_queries: string[]
}

interface SeoQueryPipelineQueryAssignmentItem {
  normalized_query_text: string
  ranking_value_used: string
  query_type: 'head' | 'mid' | 'tail'
  lexical_cluster_label_candidate: string
  lexical_cluster_query_count: number
  semantic_cluster_label_candidate: string
  semantic_cluster_query_count: number
  semantic_kind: string
}

interface SeoQueryPipelineSemanticDiagnostics {
  project_id: number
  category_id: number
  model_name: string
  clustering_backend: string
  similarity_threshold: string
  min_community_size: number
  gating_strategy: string
  strategy_label: string
  total_input_queries: number
  total_semantic_clusters: number
  multi_member_cluster_count: number
  singleton_noise_count: number
  average_cluster_size: string
  biggest_cluster_size: number
  segment_count: number
  largest_segment_size: number
  counts_by_query_type: Record<string, number>
  cluster_size_distribution: Record<string, number>
  top_segments: Array<{
    segment_key: string
    query_count: number
  }>
  top_semantic_clusters: SeoQueryPipelineCompareClusterItem[]
  sample_noise_queries: Array<{
    normalized_query_text: string
    display_query: string
    ranking_value_used: string
    query_type: 'head' | 'mid' | 'tail'
    intent_type: string
  }>
}

interface SeoQueryPipelineComparisonDiagnostics {
  project_id: number
  category_id: number
  total_input_queries: number
  total_lexical_clusters: number
  total_semantic_clusters: number
  lexical_singleton_count: number
  semantic_singleton_noise_count: number
  top_lexical_clusters: SeoQueryPipelineCompareClusterItem[]
  top_semantic_clusters: SeoQueryPipelineCompareClusterItem[]
  semantic_overbroad_cases: SeoQueryPipelineSemanticOverbroadCase[]
  semantic_grouped_fragment_cases: SeoQueryPipelineSemanticGroupingCase[]
  top_query_assignments: SeoQueryPipelineQueryAssignmentItem[]
}

interface SeoQueryPipelineLexicalSummary {
  total_clusters: number
  singleton_cluster_count: number
  average_cluster_size: string
  biggest_cluster_size: number
  cluster_size_distribution: Record<string, number>
}

interface SeoQueryPipelineSemanticImprovementSummary {
  raw_biggest_cluster_size: number
  gated_biggest_cluster_size: number
  biggest_cluster_reduction: number
  raw_total_clusters: number
  gated_total_clusters: number
  raw_singleton_noise_count: number
  gated_singleton_noise_count: number
}

interface SeoQueryPipelineCompare {
  project_id: number
  category_id: number
  bucket: string | null
  model_name: string
  strategy: string
  available_strategies: Record<string, string>
  lexical_summary: SeoQueryPipelineLexicalSummary
  raw_semantic: SeoQueryPipelineSemanticDiagnostics
  raw_comparison: SeoQueryPipelineComparisonDiagnostics
  gated_semantic: SeoQueryPipelineSemanticDiagnostics
  gated_comparison: SeoQueryPipelineComparisonDiagnostics
  improvement_summary: SeoQueryPipelineSemanticImprovementSummary
}

const STATUS_OPTIONS: PruningStatus[] = ['keep', 'drop', 'review']
const BUCKET_OPTIONS: BucketFilter[] = ['all', 'head', 'mid', 'tail']
const INTENT_OPTIONS: IntentFilter[] = ['all', 'product', 'category', 'informational', 'garbage', 'unknown']
const HYBRID_PROVENANCE_OPTIONS: HybridProvenanceFilter[] = ['all', 'individual', 'cluster', 'rejected', 'fallback']
const PAGE_SIZE = 25
const DEFAULT_SEMANTIC_STRATEGY = 'anchor_family_gate'

function parseTab(rawValue: string | null): QueryTab {
  if (
    rawValue === 'clusters' ||
    rawValue === 'audit' ||
    rawValue === 'compare' ||
    rawValue === 'hybrid' ||
    rawValue === 'profiles' ||
    rawValue === 'scoring_prep' ||
    rawValue === 'scoring'
  ) {
    return rawValue
  }
  return 'queries'
}

function formatNumber(value: string | number): string {
  const numeric = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(numeric)) return String(value)
  return new Intl.NumberFormat('ru-RU', {
    minimumFractionDigits: Number.isInteger(numeric) ? 0 : 2,
    maximumFractionDigits: Number.isInteger(numeric) ? 0 : 2,
  }).format(numeric)
}

function badgeStyle(background: string, color: string) {
  return {
    display: 'inline-flex',
    alignItems: 'center',
    padding: '4px 8px',
    borderRadius: 999,
    fontSize: 12,
    fontWeight: 600,
    background,
    color,
    whiteSpace: 'nowrap' as const,
  }
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms)
  })
}

function normalizeApiErrorMessage(detail: unknown, fallback: string): string {
  if (typeof detail === 'string' && detail.trim()) {
    return detail
  }
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0]
    if (typeof first === 'string' && first.trim()) {
      return first
    }
    if (first && typeof first === 'object') {
      const message = (first as { msg?: unknown }).msg
      if (typeof message === 'string' && message.trim()) {
        return message
      }
    }
  }
  if (detail && typeof detail === 'object') {
    const message = (detail as { msg?: unknown }).msg
    if (typeof message === 'string' && message.trim()) {
      return message
    }
  }
  return fallback
}

async function fetchDebugDataWithRetry(
  requestKey: string,
  retryCount: number,
): Promise<SeoQueryPipelineDebugResponse> {
  let lastError: unknown = null
  for (let attempt = 0; attempt <= retryCount; attempt += 1) {
    try {
      return await apiGetData<SeoQueryPipelineDebugResponse>(requestKey)
    } catch (error) {
      lastError = error
      if (attempt >= retryCount) {
        break
      }
      await delay(1200 * (attempt + 1))
    }
  }
  throw lastError
}

async function fetchSubjectsWithRetry(
  projectId: string,
  retryCount: number,
): Promise<WBProductSubjectItem[]> {
  let lastError: unknown = null
  for (let attempt = 0; attempt <= retryCount; attempt += 1) {
    try {
      return await getWBProductSubjects(projectId)
    } catch (error) {
      lastError = error
      if (attempt >= retryCount) {
        break
      }
      await delay(1000 * (attempt + 1))
    }
  }
  throw lastError
}

function BucketBadge({ value }: { value: 'head' | 'mid' | 'tail' }) {
  if (value === 'head') {
    return <span style={badgeStyle('#dbeafe', '#1d4ed8')}>head</span>
  }
  if (value === 'mid') {
    return <span style={badgeStyle('#fef3c7', '#b45309')}>mid</span>
  }
  return <span style={badgeStyle('#e5e7eb', '#374151')}>tail</span>
}

function PruningBadge({ value }: { value: PruningStatus }) {
  if (value === 'keep') {
    return <span style={badgeStyle('#dcfce7', '#166534')}>keep</span>
  }
  if (value === 'drop') {
    return <span style={badgeStyle('#fee2e2', '#991b1b')}>drop</span>
  }
  return <span style={badgeStyle('#fef3c7', '#92400e')}>review</span>
}

function IntentBadge({ value }: { value: string }) {
  return <span style={badgeStyle('#f3f4f6', '#111827')}>{value}</span>
}

function ProvenanceBadge({ value }: { value: SeoQueryPipelineHybridItem['provenance'] }) {
  if (value === 'individual') {
    return <span style={badgeStyle('#dbeafe', '#1d4ed8')}>individual</span>
  }
  if (value === 'cluster') {
    return <span style={badgeStyle('#dcfce7', '#166534')}>cluster</span>
  }
  if (value === 'fallback') {
    return <span style={badgeStyle('#fef3c7', '#b45309')}>fallback</span>
  }
  return <span style={badgeStyle('#fee2e2', '#991b1b')}>rejected</span>
}

function AnchorBadge({ value }: { value: boolean }) {
  if (value) {
    return <span style={badgeStyle('#dcfce7', '#166534')}>anchor</span>
  }
  return <span style={badgeStyle('#f3f4f6', '#6b7280')}>member</span>
}

function ProfileStrengthBadge({ value }: { value: SeoQueryPipelineProfileItem['profile_strength'] }) {
  if (value === 'strong') {
    return <span style={badgeStyle('#dcfce7', '#166534')}>strong</span>
  }
  if (value === 'medium') {
    return <span style={badgeStyle('#dbeafe', '#1d4ed8')}>medium</span>
  }
  if (value === 'weak') {
    return <span style={badgeStyle('#fef3c7', '#b45309')}>weak</span>
  }
  return <span style={badgeStyle('#fee2e2', '#991b1b')}>empty</span>
}

function ReadinessBadge({ value }: { value: SeoQueryPipelineScoringPrepItem['readiness_for_scoring'] }) {
  if (value === 'ready') {
    return <span style={badgeStyle('#dcfce7', '#166534')}>ready</span>
  }
  if (value === 'partial') {
    return <span style={badgeStyle('#fef3c7', '#b45309')}>partial</span>
  }
  return <span style={badgeStyle('#fee2e2', '#991b1b')}>poor</span>
}

function ProductTypeMatchBadge({ value }: { value: SeoQueryPipelineScoringPrepProductTypeMatchItem['status'] }) {
  if (value === 'matched') {
    return <span style={badgeStyle('#dcfce7', '#166534')}>matched</span>
  }
  if (value === 'not_matched') {
    return <span style={badgeStyle('#fee2e2', '#991b1b')}>not matched</span>
  }
  return <span style={badgeStyle('#f3f4f6', '#6b7280')}>unknown</span>
}

function formatScoringPrepSummary(match: SeoQueryPipelineScoringPrepUseCaseMatchItem | SeoQueryPipelineScoringPrepAttributeMatchItem): string {
  const matched = match.matched_markers.length
  const missed = match.missed_markers.length
  const unknown = match.unknown_markers.length
  const conflicting = 'conflicting_markers' in match ? match.conflicting_markers.length : 0
  if (matched + missed + unknown + conflicting === 0) return '—'
  const parts = [`m:${matched}`]
  if (conflicting > 0) parts.push(`c:${conflicting}`)
  parts.push(`x:${missed}`)
  parts.push(`u:${unknown}`)
  return parts.join(' · ')
}

function formatScoringPrepFlags(flags: SeoQueryPipelineScoringPrepFlags): string {
  const activeFlags = Object.entries(flags)
    .filter(([, value]) => Boolean(value))
    .map(([key]) => key)
  return activeFlags.length > 0 ? activeFlags.join(', ') : '—'
}

function formatEvidenceFields(summary: SeoQueryPipelineScoringPrepSkuEvidenceSummary): string {
  if (summary.normalized_evidence_fields_used.length === 0) return '—'
  return summary.normalized_evidence_fields_used.join(', ')
}

function formatScoringPrepMarker(item: SeoQueryPipelineScoringPrepMarkerItem): string {
  const familyPart = item.family ? ` (${item.family})` : ''
  const conflictPart = item.conflicting_with.length > 0 ? ` vs ${item.conflicting_with.join(', ')}` : ''
  return `${item.status} | ${item.value}${familyPart}${conflictPart} | ${item.reason}`
}

function formatActualScoreBreakdown(item: SeoQueryPipelineActualScoringItem): string {
  return `t:${item.product_type_score} · u:${item.use_case_score} · a:${item.attribute_score}`
}

function formatActualPenalties(item: SeoQueryPipelineActualScoringItem): string {
  if (item.penalties.length === 0) return '—'
  return item.penalties.map((penalty) => `${penalty.name}:${penalty.value}`).join(', ')
}

function formatProfileMarkers(markers: SeoQueryProfileMarkerItem[]): string {
  if (markers.length === 0) return '—'
  return markers
    .slice(0, 3)
    .map((marker) => (marker.family ? `${marker.value} (${marker.family})` : marker.value))
    .join(', ')
}

function formatMarkerDecision(item: SeoQueryProfileMarkerDecisionItem): string {
  const familyPart = item.family ? ` (${item.family})` : ''
  const sources = item.source_kinds.length > 0 ? item.source_kinds.join('/') : '—'
  return `${item.selected ? 'selected' : 'rejected'} | ${item.slot} | ${item.value}${familyPart} | q=${item.support_query_count} r=${formatNumber(item.support_ratio)} | src=${sources} | ${item.reason}`
}

function Pagination({
  page,
  totalPages,
  onChange,
}: {
  page: number
  totalPages: number
  onChange: (page: number) => void
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 16 }}>
      <div style={{ fontSize: 13, color: '#6b7280' }}>
        Страница {totalPages === 0 ? 0 : page} из {totalPages}
      </div>
      <div style={{ display: 'flex', gap: 8 }}>
        <button
          type="button"
          onClick={() => onChange(page - 1)}
          disabled={page <= 1}
          style={{
            padding: '8px 12px',
            borderRadius: 8,
            border: '1px solid #d1d5db',
            background: page <= 1 ? '#f9fafb' : '#fff',
            color: page <= 1 ? '#9ca3af' : '#111827',
            cursor: page <= 1 ? 'not-allowed' : 'pointer',
          }}
        >
          Назад
        </button>
        <button
          type="button"
          onClick={() => onChange(page + 1)}
          disabled={page >= totalPages}
          style={{
            padding: '8px 12px',
            borderRadius: 8,
            border: '1px solid #d1d5db',
            background: page >= totalPages ? '#f9fafb' : '#fff',
            color: page >= totalPages ? '#9ca3af' : '#111827',
            cursor: page >= totalPages ? 'not-allowed' : 'pointer',
          }}
        >
          Вперёд
        </button>
      </div>
    </div>
  )
}

function AuditStatList({
  title,
  items,
}: {
  title: string
  items: Array<[string, string | number]>
}) {
  return (
    <div
      className="card"
      style={{
        padding: 16,
        borderRadius: 12,
        border: '1px solid #e5e7eb',
        background: '#fff',
      }}
    >
      <div style={{ fontSize: 14, fontWeight: 700, color: '#111827', marginBottom: 12 }}>{title}</div>
      {items.length === 0 ? (
        <div style={{ color: '#6b7280', fontSize: 14 }}>Нет данных.</div>
      ) : (
        <div style={{ display: 'grid', gap: 10 }}>
          {items.map(([label, value]) => (
            <div
              key={label}
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                gap: 12,
                paddingBottom: 10,
                borderBottom: '1px solid #f3f4f6',
              }}
            >
              <span style={{ color: '#374151', fontSize: 14 }}>{label}</span>
              <span style={{ color: '#111827', fontWeight: 600 }}>{formatNumber(value)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function AuditQueryTable({
  title,
  rows,
}: {
  title: string
  rows: SeoQueryPipelineAuditQueryItem[]
}) {
  return (
    <div
      className="card"
      style={{
        borderRadius: 12,
        border: '1px solid #e5e7eb',
        background: '#fff',
        overflow: 'hidden',
      }}
    >
      <div style={{ padding: '16px 16px 0', fontSize: 14, fontWeight: 700, color: '#111827' }}>{title}</div>
      <div style={{ overflowX: 'auto', padding: 16 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 920 }}>
          <thead style={{ background: '#f9fafb' }}>
            <tr>
              {['query', 'ranking', 'bucket', 'intent', 'reason', 'flags'].map((label) => (
                <th
                  key={label}
                  style={{
                    textAlign: 'left',
                    padding: '12px 14px',
                    fontSize: 12,
                    textTransform: 'uppercase',
                    letterSpacing: 0.4,
                    color: '#6b7280',
                    borderBottom: '1px solid #e5e7eb',
                  }}
                >
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={6} style={{ padding: 24, color: '#6b7280' }}>
                  Нет строк для этого audit-среза.
                </td>
              </tr>
            ) : (
              rows.map((item) => (
                <tr key={`${title}:${item.normalized_query_text}`} style={{ borderBottom: '1px solid #f3f4f6' }}>
                  <td style={{ padding: '14px', color: '#111827', fontWeight: 600 }}>{item.normalized_query_text}</td>
                  <td style={{ padding: '14px', color: '#111827' }}>{formatNumber(item.ranking_value_used)}</td>
                  <td style={{ padding: '14px' }}><BucketBadge value={item.query_type} /></td>
                  <td style={{ padding: '14px' }}><IntentBadge value={item.intent_type} /></td>
                  <td style={{ padding: '14px', color: '#374151' }}>
                    {item.issue_reason || item.pruning_reason_code || '—'}
                  </td>
                  <td style={{ padding: '14px', color: '#6b7280', fontSize: 13 }}>
                    {item.preparation_flag_reasons.length > 0 ? item.preparation_flag_reasons.join(', ') : '—'}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function AuditClusterTable({
  title,
  rows,
}: {
  title: string
  rows: SeoQueryPipelineAuditClusterItem[]
}) {
  return (
    <div
      className="card"
      style={{
        borderRadius: 12,
        border: '1px solid #e5e7eb',
        background: '#fff',
        overflow: 'hidden',
      }}
    >
      <div style={{ padding: '16px 16px 0', fontSize: 14, fontWeight: 700, color: '#111827' }}>{title}</div>
      <div style={{ overflowX: 'auto', padding: 16 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 980 }}>
          <thead style={{ background: '#f9fafb' }}>
            <tr>
              {['label', 'query_count', 'top_ranking', 'head', 'mid', 'tail', 'issue', 'members'].map((label) => (
                <th
                  key={label}
                  style={{
                    textAlign: 'left',
                    padding: '12px 14px',
                    fontSize: 12,
                    textTransform: 'uppercase',
                    letterSpacing: 0.4,
                    color: '#6b7280',
                    borderBottom: '1px solid #e5e7eb',
                  }}
                >
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={8} style={{ padding: 24, color: '#6b7280' }}>
                  Нет строк для этого audit-среза.
                </td>
              </tr>
            ) : (
              rows.map((item) => (
                <tr key={`${title}:${item.cluster_key}`} style={{ borderBottom: '1px solid #f3f4f6' }}>
                  <td style={{ padding: '14px', color: '#111827', fontWeight: 600 }}>{item.cluster_label_candidate}</td>
                  <td style={{ padding: '14px', color: '#111827' }}>{formatNumber(item.query_count)}</td>
                  <td style={{ padding: '14px', color: '#111827' }}>{formatNumber(item.top_member_ranking_value_used)}</td>
                  <td style={{ padding: '14px', color: '#111827' }}>{formatNumber(item.head_query_count)}</td>
                  <td style={{ padding: '14px', color: '#111827' }}>{formatNumber(item.mid_query_count)}</td>
                  <td style={{ padding: '14px', color: '#111827' }}>{formatNumber(item.tail_query_count)}</td>
                  <td style={{ padding: '14px', color: '#374151' }}>{item.issue_reason || '—'}</td>
                  <td style={{ padding: '14px', color: '#6b7280', fontSize: 13 }}>
                    {item.member_samples.length > 0 ? item.member_samples.join(', ') : '—'}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function AuditClusterPairTable({
  title,
  rows,
}: {
  title: string
  rows: SeoQueryPipelineAuditClusterPairItem[]
}) {
  return (
    <div
      className="card"
      style={{
        borderRadius: 12,
        border: '1px solid #e5e7eb',
        background: '#fff',
        overflow: 'hidden',
      }}
    >
      <div style={{ padding: '16px 16px 0', fontSize: 14, fontWeight: 700, color: '#111827' }}>{title}</div>
      <div style={{ overflowX: 'auto', padding: 16 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 920 }}>
          <thead style={{ background: '#f9fafb' }}>
            <tr>
              {['cluster_a', 'count_a', 'cluster_b', 'count_b', 'similarity', 'basis'].map((label) => (
                <th
                  key={label}
                  style={{
                    textAlign: 'left',
                    padding: '12px 14px',
                    fontSize: 12,
                    textTransform: 'uppercase',
                    letterSpacing: 0.4,
                    color: '#6b7280',
                    borderBottom: '1px solid #e5e7eb',
                  }}
                >
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={6} style={{ padding: 24, color: '#6b7280' }}>
                  Нет похожих candidate pairs.
                </td>
              </tr>
            ) : (
              rows.map((item) => (
                <tr key={`${item.cluster_key_a}:${item.cluster_key_b}`} style={{ borderBottom: '1px solid #f3f4f6' }}>
                  <td style={{ padding: '14px', color: '#111827', fontWeight: 600 }}>{item.cluster_label_candidate_a}</td>
                  <td style={{ padding: '14px', color: '#111827' }}>{formatNumber(item.query_count_a)}</td>
                  <td style={{ padding: '14px', color: '#111827', fontWeight: 600 }}>{item.cluster_label_candidate_b}</td>
                  <td style={{ padding: '14px', color: '#111827' }}>{formatNumber(item.query_count_b)}</td>
                  <td style={{ padding: '14px', color: '#111827' }}>{formatNumber(item.similarity_score)}</td>
                  <td style={{ padding: '14px', color: '#374151' }}>{item.similarity_basis}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function LexicalImprovementTable({
  rows,
}: {
  rows: SeoQueryPipelineLexicalImprovedQueryCase[]
}) {
  return (
    <div
      className="card"
      style={{
        borderRadius: 12,
        border: '1px solid #e5e7eb',
        background: '#fff',
        overflow: 'hidden',
      }}
    >
      <div style={{ padding: '16px 16px 0', fontSize: 14, fontWeight: 700, color: '#111827' }}>
        Improved Query Cases
      </div>
      <div style={{ overflowX: 'auto', padding: 16 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 980 }}>
          <thead style={{ background: '#f9fafb' }}>
            <tr>
              {['query', 'ranking', 'legacy_cluster', 'legacy_count', 'tightened_cluster', 'tightened_count'].map((label) => (
                <th
                  key={label}
                  style={{
                    textAlign: 'left',
                    padding: '12px 14px',
                    fontSize: 12,
                    textTransform: 'uppercase',
                    letterSpacing: 0.4,
                    color: '#6b7280',
                    borderBottom: '1px solid #e5e7eb',
                  }}
                >
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={6} style={{ padding: 24, color: '#6b7280' }}>
                  Нет улучшенных query cases.
                </td>
              </tr>
            ) : (
              rows.map((item) => (
                <tr key={item.normalized_query_text} style={{ borderBottom: '1px solid #f3f4f6' }}>
                  <td style={{ padding: '14px', color: '#111827', fontWeight: 600 }}>{item.normalized_query_text}</td>
                  <td style={{ padding: '14px', color: '#111827' }}>{formatNumber(item.ranking_value_used)}</td>
                  <td style={{ padding: '14px', color: '#374151' }}>{item.legacy_cluster_label_candidate}</td>
                  <td style={{ padding: '14px', color: '#111827' }}>{formatNumber(item.legacy_cluster_query_count)}</td>
                  <td style={{ padding: '14px', color: '#374151' }}>{item.tightened_cluster_label_candidate}</td>
                  <td style={{ padding: '14px', color: '#111827' }}>{formatNumber(item.tightened_cluster_query_count)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function CompareClusterTable({
  title,
  rows,
}: {
  title: string
  rows: SeoQueryPipelineCompareClusterItem[]
}) {
  return (
    <div
      className="card"
      style={{
        borderRadius: 12,
        border: '1px solid #e5e7eb',
        background: '#fff',
        overflow: 'hidden',
      }}
    >
      <div style={{ padding: '16px 16px 0', fontSize: 14, fontWeight: 700, color: '#111827' }}>{title}</div>
      <div style={{ overflowX: 'auto', padding: 16 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 980 }}>
          <thead style={{ background: '#f9fafb' }}>
            <tr>
              {['label', 'query_count', 'kind', 'head', 'mid', 'tail', 'members'].map((label) => (
                <th
                  key={label}
                  style={{
                    textAlign: 'left',
                    padding: '12px 14px',
                    fontSize: 12,
                    textTransform: 'uppercase',
                    letterSpacing: 0.4,
                    color: '#6b7280',
                    borderBottom: '1px solid #e5e7eb',
                  }}
                >
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={7} style={{ padding: 24, color: '#6b7280' }}>
                  Нет кластеров для этого comparison-среза.
                </td>
              </tr>
            ) : (
              rows.map((item) => (
                <tr key={`${title}:${item.cluster_key}`} style={{ borderBottom: '1px solid #f3f4f6' }}>
                  <td style={{ padding: '14px', color: '#111827', fontWeight: 600 }}>{item.cluster_label_candidate}</td>
                  <td style={{ padding: '14px', color: '#111827' }}>{formatNumber(item.query_count)}</td>
                  <td style={{ padding: '14px', color: '#374151' }}>{item.semantic_kind}</td>
                  <td style={{ padding: '14px', color: '#111827' }}>{formatNumber(item.head_query_count)}</td>
                  <td style={{ padding: '14px', color: '#111827' }}>{formatNumber(item.mid_query_count)}</td>
                  <td style={{ padding: '14px', color: '#111827' }}>{formatNumber(item.tail_query_count)}</td>
                  <td style={{ padding: '14px', color: '#6b7280', fontSize: 13 }}>
                    {item.member_samples.length > 0 ? item.member_samples.join(', ') : '—'}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function CompareCaseTable({
  title,
  rows,
  mode,
}: {
  title: string
  rows: SeoQueryPipelineSemanticOverbroadCase[] | SeoQueryPipelineSemanticGroupingCase[]
  mode: 'overbroad' | 'grouped'
}) {
  return (
    <div
      className="card"
      style={{
        borderRadius: 12,
        border: '1px solid #e5e7eb',
        background: '#fff',
        overflow: 'hidden',
      }}
    >
      <div style={{ padding: '16px 16px 0', fontSize: 14, fontWeight: 700, color: '#111827' }}>{title}</div>
      <div style={{ overflowX: 'auto', padding: 16 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 980 }}>
          <thead style={{ background: '#f9fafb' }}>
            <tr>
              {[
                'semantic_cluster',
                'lexical_groups',
                'query_count',
                mode === 'overbroad' ? 'dominant/share' : 'notes',
                'groups',
                'samples',
              ].map((label) => (
                <th
                  key={label}
                  style={{
                    textAlign: 'left',
                    padding: '12px 14px',
                    fontSize: 12,
                    textTransform: 'uppercase',
                    letterSpacing: 0.4,
                    color: '#6b7280',
                    borderBottom: '1px solid #e5e7eb',
                  }}
                >
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={6} style={{ padding: 24, color: '#6b7280' }}>
                  Нет disagreement cases.
                </td>
              </tr>
            ) : (
              rows.map((item) => {
                const clusterLabel = item.semantic_cluster_label_candidate
                const groupCount = item.lexical_group_count
                const queryCount = item.semantic_query_count
                const share =
                  mode === 'overbroad'
                    ? (item as SeoQueryPipelineSemanticOverbroadCase).dominant_lexical_group_share
                    : 'fragment_merge_candidate'
                const groups = item.lexical_groups
                const samples = item.sample_queries
                return (
                  <tr key={`${title}:${clusterLabel}`} style={{ borderBottom: '1px solid #f3f4f6' }}>
                    <td style={{ padding: '14px', color: '#111827', fontWeight: 600 }}>{clusterLabel}</td>
                    <td style={{ padding: '14px', color: '#111827' }}>{formatNumber(groupCount)}</td>
                    <td style={{ padding: '14px', color: '#111827' }}>{formatNumber(queryCount)}</td>
                    <td style={{ padding: '14px', color: '#374151' }}>{share}</td>
                    <td style={{ padding: '14px', color: '#374151', fontSize: 13 }}>
                      {groups.map((group) => `${group.cluster_label_candidate} (${group.query_count})`).join(', ')}
                    </td>
                    <td style={{ padding: '14px', color: '#6b7280', fontSize: 13 }}>{samples.join(', ')}</td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function CompareAssignmentTable({
  title,
  rows,
}: {
  title: string
  rows: SeoQueryPipelineQueryAssignmentItem[]
}) {
  return (
    <div
      className="card"
      style={{
        borderRadius: 12,
        border: '1px solid #e5e7eb',
        background: '#fff',
        overflow: 'hidden',
      }}
    >
      <div style={{ padding: '16px 16px 0', fontSize: 14, fontWeight: 700, color: '#111827' }}>{title}</div>
      <div style={{ overflowX: 'auto', padding: 16 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 1100 }}>
          <thead style={{ background: '#f9fafb' }}>
            <tr>
              {['query', 'ranking', 'bucket', 'lexical_cluster', 'lexical_count', 'semantic_cluster', 'semantic_count', 'semantic_kind'].map((label) => (
                <th
                  key={label}
                  style={{
                    textAlign: 'left',
                    padding: '12px 14px',
                    fontSize: 12,
                    textTransform: 'uppercase',
                    letterSpacing: 0.4,
                    color: '#6b7280',
                    borderBottom: '1px solid #e5e7eb',
                  }}
                >
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={8} style={{ padding: 24, color: '#6b7280' }}>
                  Нет side-by-side query samples.
                </td>
              </tr>
            ) : (
              rows.map((item) => (
                <tr key={item.normalized_query_text} style={{ borderBottom: '1px solid #f3f4f6' }}>
                  <td style={{ padding: '14px', color: '#111827', fontWeight: 600 }}>{item.normalized_query_text}</td>
                  <td style={{ padding: '14px', color: '#111827' }}>{formatNumber(item.ranking_value_used)}</td>
                  <td style={{ padding: '14px' }}><BucketBadge value={item.query_type} /></td>
                  <td style={{ padding: '14px', color: '#374151' }}>{item.lexical_cluster_label_candidate}</td>
                  <td style={{ padding: '14px', color: '#111827' }}>{formatNumber(item.lexical_cluster_query_count)}</td>
                  <td style={{ padding: '14px', color: '#374151' }}>{item.semantic_cluster_label_candidate}</td>
                  <td style={{ padding: '14px', color: '#111827' }}>{formatNumber(item.semantic_cluster_query_count)}</td>
                  <td style={{ padding: '14px', color: '#374151' }}>{item.semantic_kind}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default function SeoQueryPipelineDebugPage({ params }: { params: { projectId: string } }) {
  const projectId = params.projectId
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()

  const initialTab = parseTab(searchParams.get('tab'))
  const initialCategoryId = searchParams.get('category_id') || ''
  const initialSemanticStrategy = searchParams.get('strategy') || DEFAULT_SEMANTIC_STRATEGY
  const initialScoringPrepNmId = searchParams.get('nm_id') || ''

  usePageTitle('SEO Pipeline', projectId)

  const [activeTab, setActiveTab] = useState<QueryTab>(initialTab)
  const [categoryId, setCategoryId] = useState(initialCategoryId)
  const [subjects, setSubjects] = useState<WBProductSubjectItem[]>([])
  const [subjectsLoading, setSubjectsLoading] = useState(false)
  const [data, setData] = useState<SeoQueryPipelineDebugResponse | null>(null)
  const [loadedRequestKey, setLoadedRequestKey] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [selectedStatuses, setSelectedStatuses] = useState<Set<PruningStatus>>(new Set(STATUS_OPTIONS))
  const [selectedBucket, setSelectedBucket] = useState<BucketFilter>('all')
  const [selectedIntent, setSelectedIntent] = useState<IntentFilter>('all')
  const [searchValue, setSearchValue] = useState('')
  const deferredSearchValue = useDeferredValue(searchValue)
  const [queriesPage, setQueriesPage] = useState(1)
  const [clustersPage, setClustersPage] = useState(1)
  const [hybridPage, setHybridPage] = useState(1)
  const [profilesPage, setProfilesPage] = useState(1)
  const [scoringPrepPage, setScoringPrepPage] = useState(1)
  const [actualScoringPage, setActualScoringPage] = useState(1)
  const [expandedClusters, setExpandedClusters] = useState<Set<string>>(new Set())
  const [selectedSemanticStrategy, setSelectedSemanticStrategy] = useState(initialSemanticStrategy)
  const [selectedHybridProvenance, setSelectedHybridProvenance] = useState<HybridProvenanceFilter>('all')
  const [selectedHybridBucket, setSelectedHybridBucket] = useState<BucketFilter>('all')
  const [hybridClusterKey, setHybridClusterKey] = useState('')
  const [selectedHybridOnlyAnchors, setSelectedHybridOnlyAnchors] = useState(false)
  const [selectedHybridOnlyFallback, setSelectedHybridOnlyFallback] = useState(false)
  const [expandedHybridClusters, setExpandedHybridClusters] = useState<Set<string>>(new Set())
  const [expandedProfiles, setExpandedProfiles] = useState<Set<string>>(new Set())
  const [scoringPrepSkuQuery, setScoringPrepSkuQuery] = useState('')
  const [scoringPrepNmId, setScoringPrepNmId] = useState(initialScoringPrepNmId)
  const [selectedScoringPrepSku, setSelectedScoringPrepSku] = useState<WBProductLookupItem | null>(null)

  const buildDebugUrl = (tabValue: QueryTab, pageValue: number) => {
    const qs = new URLSearchParams()
    qs.set('category_id', categoryId)
    qs.set('tab', tabValue)
    qs.set('page', String(pageValue))
    qs.set('page_size', String(PAGE_SIZE))
    if (tabValue === 'queries') {
      qs.set('pruning_statuses', Array.from(selectedStatuses).sort().join(','))
      qs.set('bucket', selectedBucket)
      qs.set('intent', selectedIntent)
      const normalizedSearch = deferredSearchValue.trim()
      if (normalizedSearch) {
        qs.set('search', normalizedSearch)
      }
    }
    if (tabValue === 'hybrid') {
      if (selectedHybridProvenance !== 'all') {
        qs.set('hybrid_provenances', selectedHybridProvenance)
      }
      qs.set('hybrid_bucket', selectedHybridBucket)
      if (selectedHybridOnlyAnchors) {
        qs.set('hybrid_only_anchors', '1')
      }
      if (selectedHybridOnlyFallback) {
        qs.set('hybrid_only_fallback', '1')
      }
      const normalizedClusterKey = hybridClusterKey.trim()
      if (normalizedClusterKey) {
        qs.set('hybrid_cluster_key', normalizedClusterKey)
      }
    }
    if (tabValue === 'compare') {
      qs.set('strategy', selectedSemanticStrategy)
    }
    if ((tabValue === 'scoring_prep' || tabValue === 'scoring') && scoringPrepNmId) {
      qs.set('nm_id', scoringPrepNmId)
    }
    return `/api/v1/projects/${projectId}/seo/query-pipeline/debug?${qs.toString()}`
  }
  const activePage =
    activeTab === 'queries'
      ? queriesPage
      : activeTab === 'clusters'
        ? clustersPage
        : activeTab === 'hybrid'
          ? hybridPage
          : activeTab === 'profiles'
            ? profilesPage
            : activeTab === 'scoring_prep'
              ? scoringPrepPage
              : activeTab === 'scoring'
                ? actualScoringPage
              : 1
  const currentRequestKey =
    categoryId && ((activeTab !== 'scoring_prep' && activeTab !== 'scoring') || scoringPrepNmId)
      ? buildDebugUrl(activeTab, activePage)
      : null

  useEffect(() => {
    const nextTab = parseTab(searchParams.get('tab'))
    const nextCategoryId = searchParams.get('category_id') || ''
    const nextSemanticStrategy = searchParams.get('strategy') || DEFAULT_SEMANTIC_STRATEGY
    const nextScoringPrepNmId = searchParams.get('nm_id') || ''
    setActiveTab((current) => (current === nextTab ? current : nextTab))
    setCategoryId((current) => (current === nextCategoryId ? current : nextCategoryId))
    setSelectedSemanticStrategy((current) => (current === nextSemanticStrategy ? current : nextSemanticStrategy))
    setScoringPrepNmId((current) => (current === nextScoringPrepNmId ? current : nextScoringPrepNmId))
  }, [searchParams])

  useEffect(() => {
    setSubjectsLoading(true)
    fetchSubjectsWithRetry(projectId, 2)
      .then((items) => {
        setSubjects(items)
        if (!categoryId && items.length === 1) {
          setCategoryId(String(items[0].subject_id))
        }
      })
      .catch(() => {
        setSubjects([])
      })
      .finally(() => {
        setSubjectsLoading(false)
      })
  }, [projectId])

  useEffect(() => {
    const paramsState = new URLSearchParams(searchParams.toString())
    if (categoryId) {
      paramsState.set('category_id', categoryId)
    } else {
      paramsState.delete('category_id')
    }
    paramsState.set('tab', activeTab)
    if (activeTab === 'compare') {
      paramsState.set('strategy', selectedSemanticStrategy)
    } else {
      paramsState.delete('strategy')
    }
    if (scoringPrepNmId) {
      paramsState.set('nm_id', scoringPrepNmId)
    } else {
      paramsState.delete('nm_id')
    }
    const nextUrl = `${pathname}?${paramsState.toString()}`
    const currentUrl = `${pathname}?${searchParams.toString()}`
    if (nextUrl !== currentUrl) {
      router.replace(nextUrl, { scroll: false })
    }
  }, [activeTab, categoryId, pathname, router, scoringPrepNmId, searchParams, selectedSemanticStrategy])

  useEffect(() => {
    if (!categoryId || !currentRequestKey) {
      setData(null)
      setLoadedRequestKey(null)
      setError(null)
      setLoading(false)
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)
    const requestKey = currentRequestKey
    const retryCount = activeTab === 'audit' || activeTab === 'compare' ? 2 : 0
    fetchDebugDataWithRetry(requestKey, retryCount)
      .then((response) => {
        if (!cancelled) {
          setData(response)
          setLoadedRequestKey(requestKey)
        }
      })
      .catch((rawError: unknown) => {
        const apiError = rawError as ApiError
        if (!cancelled) {
          setLoadedRequestKey(null)
          setError(normalizeApiErrorMessage(apiError?.detail, 'Не удалось загрузить SEO pipeline debug.'))
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [
    activeTab,
    activePage,
    categoryId,
    deferredSearchValue,
    projectId,
    selectedSemanticStrategy,
    selectedBucket,
    selectedHybridBucket,
    selectedHybridOnlyAnchors,
    selectedHybridOnlyFallback,
    selectedHybridProvenance,
    selectedIntent,
    selectedStatuses,
    scoringPrepNmId,
    hybridClusterKey,
    currentRequestKey,
  ])

  useEffect(() => {
    setQueriesPage(1)
  }, [selectedStatuses, selectedBucket, selectedIntent, deferredSearchValue, categoryId])

  useEffect(() => {
    setClustersPage(1)
    setExpandedClusters(new Set())
  }, [categoryId])

  useEffect(() => {
    setHybridPage(1)
  }, [
    selectedHybridProvenance,
    selectedHybridBucket,
    selectedHybridOnlyAnchors,
    selectedHybridOnlyFallback,
    hybridClusterKey,
    categoryId,
  ])

  useEffect(() => {
    setProfilesPage(1)
    setExpandedProfiles(new Set())
  }, [categoryId])

  useEffect(() => {
    setScoringPrepPage(1)
    setExpandedProfiles(new Set())
  }, [categoryId, scoringPrepNmId])

  useEffect(() => {
    setActualScoringPage(1)
    setExpandedProfiles(new Set())
  }, [categoryId, scoringPrepNmId])

  useEffect(() => {
    setExpandedProfiles(new Set())
  }, [profilesPage])

  useEffect(() => {
    setExpandedProfiles(new Set())
  }, [scoringPrepPage])

  useEffect(() => {
    setExpandedProfiles(new Set())
  }, [actualScoringPage])

  useEffect(() => {
    setExpandedHybridClusters(new Set())
  }, [hybridPage, categoryId, selectedHybridProvenance, selectedHybridBucket, selectedHybridOnlyAnchors, selectedHybridOnlyFallback, hybridClusterKey])

  useEffect(() => {
    setExpandedClusters(new Set())
  }, [clustersPage])

  useEffect(() => {
    if (activeTab !== 'audit') {
      return
    }
    setExpandedClusters(new Set())
  }, [activeTab])

  const toggleStatus = (status: PruningStatus) => {
    setSelectedStatuses((current) => {
      const next = new Set(current)
      if (next.has(status)) {
        next.delete(status)
      } else {
        next.add(status)
      }
      if (next.size === 0) {
        return new Set([status])
      }
      return next
    })
  }

  const toggleClusterRow = (clusterKey: string) => {
    setExpandedClusters((current) => {
      const next = new Set(current)
      if (next.has(clusterKey)) {
        next.delete(clusterKey)
      } else {
        next.add(clusterKey)
      }
      return next
    })
  }

  const toggleHybridClusterRow = (clusterKey: string) => {
    setExpandedHybridClusters((current) => {
      const next = new Set(current)
      if (next.has(clusterKey)) {
        next.delete(clusterKey)
      } else {
        next.add(clusterKey)
      }
      return next
    })
  }

  const toggleProfileRow = (clusterKey: string) => {
    setExpandedProfiles((current) => {
      const next = new Set(current)
      if (next.has(clusterKey)) {
        next.delete(clusterKey)
      } else {
        next.add(clusterKey)
      }
      return next
    })
  }

  const isCurrentViewFresh = Boolean(data && currentRequestKey && loadedRequestKey === currentRequestKey)
  const queryRows = activeTab === 'queries' && isCurrentViewFresh ? data?.queries || [] : []
  const queryPagination =
    activeTab === 'queries' && isCurrentViewFresh
      ? data?.queries_pagination || { page: 1, page_size: PAGE_SIZE, total_count: 0, total_pages: 0 }
      : { page: queriesPage, page_size: PAGE_SIZE, total_count: 0, total_pages: 0 }
  const clusterRows = activeTab === 'clusters' && isCurrentViewFresh ? data?.clusters || [] : []
  const clusterPagination =
    activeTab === 'clusters' && isCurrentViewFresh
      ? data?.clusters_pagination || { page: 1, page_size: PAGE_SIZE, total_count: 0, total_pages: 0 }
      : { page: clustersPage, page_size: PAGE_SIZE, total_count: 0, total_pages: 0 }
  const hybridRows = activeTab === 'hybrid' && isCurrentViewFresh ? data?.hybrid || [] : []
  const hybridPagination =
    activeTab === 'hybrid' && isCurrentViewFresh
      ? data?.hybrid_pagination || { page: 1, page_size: PAGE_SIZE, total_count: 0, total_pages: 0 }
      : { page: hybridPage, page_size: PAGE_SIZE, total_count: 0, total_pages: 0 }
  const hybridClusterDetails = activeTab === 'hybrid' && isCurrentViewFresh ? data?.hybrid_cluster_details || [] : []
  const hybridClusterDetailsByKey = Object.fromEntries(
    hybridClusterDetails.map((detail) => [detail.cluster_key, detail] as const),
  )
  const profileRows = activeTab === 'profiles' && isCurrentViewFresh ? data?.profiles || [] : []
  const profilePagination =
    activeTab === 'profiles' && isCurrentViewFresh
      ? data?.profiles_pagination || { page: 1, page_size: PAGE_SIZE, total_count: 0, total_pages: 0 }
      : { page: profilesPage, page_size: PAGE_SIZE, total_count: 0, total_pages: 0 }
  const scoringPrepRows = activeTab === 'scoring_prep' && isCurrentViewFresh ? data?.scoring_preparations || [] : []
  const scoringPrepPagination =
    activeTab === 'scoring_prep' && isCurrentViewFresh
      ? data?.scoring_prep_pagination || { page: 1, page_size: PAGE_SIZE, total_count: 0, total_pages: 0 }
      : { page: scoringPrepPage, page_size: PAGE_SIZE, total_count: 0, total_pages: 0 }
  const actualScoringRows = activeTab === 'scoring' && isCurrentViewFresh ? data?.actual_scores || [] : []
  const actualScoringPagination =
    activeTab === 'scoring' && isCurrentViewFresh
      ? data?.actual_scoring_pagination || { page: 1, page_size: PAGE_SIZE, total_count: 0, total_pages: 0 }
      : { page: actualScoringPage, page_size: PAGE_SIZE, total_count: 0, total_pages: 0 }
  const auditData = activeTab === 'audit' && isCurrentViewFresh ? data?.audit : null
  const compareData = activeTab === 'compare' && isCurrentViewFresh ? data?.compare : null
  const hybridDiagnostics = activeTab === 'hybrid' && isCurrentViewFresh ? data?.hybrid_diagnostics : null
  const profilesDiagnostics = activeTab === 'profiles' && isCurrentViewFresh ? data?.profiles_diagnostics : null
  const scoringPrepDiagnostics = activeTab === 'scoring_prep' && isCurrentViewFresh ? data?.scoring_prep_diagnostics : null
  const actualScoringDiagnostics = activeTab === 'scoring' && isCurrentViewFresh ? data?.actual_scoring_diagnostics : null

  return (
    <div className="container" style={{ paddingBottom: 40 }}>
      <div style={{ marginBottom: 20 }}>
        <PortalBackButton fallbackHref={`/app/project/${projectId}/dashboard`} />
      </div>

      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          gap: 16,
          flexWrap: 'wrap',
          marginBottom: 20,
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            <h1 style={{ margin: 0 }}>SEO Query Pipeline</h1>
            <span style={badgeStyle('#111827', '#ffffff')}>internal debug</span>
          </div>
          <p style={{ marginTop: 8, color: '#6b7280', maxWidth: 860 }}>
            Read-only экран для просмотра clean query set, pruning/annotation и query clusters без продуктовых действий.
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <Link
            href={`/app/project/${projectId}/wildberries/seo/query-import`}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              minHeight: 40,
              padding: '0 14px',
              borderRadius: 10,
              border: '1px solid #d1d5db',
              background: '#fff',
              color: '#111827',
              textDecoration: 'none',
              fontWeight: 500,
            }}
          >
            Query Import
          </Link>
          <button
            type="button"
            onClick={() => {
              if (!categoryId) return
              setLoading(true)
              setError(null)
              const requestPage =
                activeTab === 'queries'
                  ? queriesPage
                  : activeTab === 'clusters'
                    ? clustersPage
                    : activeTab === 'hybrid'
                      ? hybridPage
                      : activeTab === 'profiles'
                        ? profilesPage
                        : activeTab === 'scoring_prep'
                          ? scoringPrepPage
                          : activeTab === 'scoring'
                            ? actualScoringPage
                        : 1
              const requestKey = buildDebugUrl(activeTab, requestPage)
              const retryCount = activeTab === 'audit' || activeTab === 'compare' ? 2 : 0
              fetchDebugDataWithRetry(requestKey, retryCount)
                .then((response) => {
                  setData(response)
                  setLoadedRequestKey(requestKey)
                })
                .catch((rawError: unknown) => {
                  const apiError = rawError as ApiError
                  setLoadedRequestKey(null)
                  setError(normalizeApiErrorMessage(apiError?.detail, 'Не удалось обновить страницу.'))
                })
                .finally(() => setLoading(false))
            }}
            disabled={!categoryId || loading || ((activeTab === 'scoring_prep' || activeTab === 'scoring') && !scoringPrepNmId)}
            style={{
              minHeight: 40,
              padding: '0 14px',
              borderRadius: 10,
              border: '1px solid #111827',
              background: '#111827',
              color: '#fff',
              fontWeight: 600,
              cursor: !categoryId || loading || ((activeTab === 'scoring_prep' || activeTab === 'scoring') && !scoringPrepNmId) ? 'not-allowed' : 'pointer',
              opacity: !categoryId || loading || ((activeTab === 'scoring_prep' || activeTab === 'scoring') && !scoringPrepNmId) ? 0.6 : 1,
            }}
          >
            {loading ? 'Загрузка...' : 'Обновить'}
          </button>
        </div>
      </div>

      <div
        className="card"
        style={{
          padding: 16,
          border: '1px solid #e5e7eb',
          borderRadius: 12,
          background: '#fff',
          marginBottom: 20,
        }}
      >
        <div style={{ display: 'flex', gap: 12, alignItems: 'end', flexWrap: 'wrap' }}>
          <div style={{ minWidth: 260 }}>
            <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 6 }}>
              Категория WB
            </label>
            <select
              value={categoryId}
              onChange={(event) => setCategoryId(event.target.value)}
              style={{
                width: '100%',
                minHeight: 42,
                borderRadius: 10,
                border: '1px solid #d1d5db',
                padding: '0 12px',
                background: '#fff',
              }}
            >
              <option value="">{subjectsLoading ? 'Загрузка категорий...' : 'Выберите категорию'}</option>
              {subjects.map((subject) => (
                <option key={subject.subject_id} value={subject.subject_id}>
                  {subject.subject_name || `Category ${subject.subject_id}`} ({subject.subject_id})
                </option>
              ))}
            </select>
          </div>
          <div style={{ color: '#6b7280', fontSize: 13, paddingBottom: 8 }}>
            Scope: `project_id = {projectId}` и `category_id = {categoryId || '—'}`
          </div>
        </div>
      </div>

      {error && (
        <div
          className="card"
          style={{
            padding: 14,
            borderRadius: 12,
            background: '#fef2f2',
            border: '1px solid #fecaca',
            color: '#991b1b',
            marginBottom: 20,
          }}
        >
          {error}
        </div>
      )}

      {data && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
            gap: 12,
            marginBottom: 20,
          }}
        >
          {[
            ['Total Queries', data.diagnostics.total_queries],
            ['Keep', data.diagnostics.keep_count],
            ['Drop', data.diagnostics.drop_count],
            ['Review', data.diagnostics.review_count],
            ['Total Clusters', data.diagnostics.total_clusters],
            ['Singleton Clusters', data.diagnostics.singleton_clusters],
          ].map(([label, value]) => (
            <div
              key={label}
              className="card"
              style={{
                padding: 16,
                borderRadius: 12,
                border: '1px solid #e5e7eb',
                background: '#fff',
              }}
            >
              <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: 0.4, color: '#6b7280' }}>
                {label}
              </div>
              <div style={{ marginTop: 8, fontSize: 28, fontWeight: 700, color: '#111827' }}>{value}</div>
            </div>
          ))}
        </div>
      )}

      <div
        className="card"
        style={{
          padding: 12,
          borderRadius: 12,
          border: '1px solid #e5e7eb',
          background: '#fff',
          marginBottom: 16,
        }}
      >
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {([
            ['queries', 'Queries'],
            ['clusters', 'Clusters'],
            ['audit', 'Audit'],
            ['compare', 'Compare'],
            ['hybrid', 'Hybrid'],
            ['profiles', 'Profiles'],
            ['scoring_prep', 'Scoring Prep'],
            ['scoring', 'Scoring'],
          ] as Array<[QueryTab, string]>).map(([tabValue, label]) => {
            const active = activeTab === tabValue
            return (
              <button
                key={tabValue}
                type="button"
                onClick={() => setActiveTab(tabValue)}
                style={{
                  minHeight: 40,
                  padding: '0 16px',
                  borderRadius: 10,
                  border: active ? '1px solid #111827' : '1px solid #d1d5db',
                  background: active ? '#111827' : '#fff',
                  color: active ? '#fff' : '#111827',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                {label}
              </button>
            )
          })}
        </div>
      </div>

      {(activeTab === 'scoring_prep' || activeTab === 'scoring') && (
        <div
          className="card"
          style={{
            padding: 16,
            borderRadius: 12,
            border: '1px solid #e5e7eb',
            background: '#fff',
            marginBottom: 16,
          }}
        >
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(280px, 420px) 1fr', gap: 16, alignItems: 'end' }}>
            <div>
              <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Target SKU</label>
              <WBProductLookupInput
                projectId={projectId}
                value={scoringPrepSkuQuery}
                onChange={(value) => {
                  setScoringPrepSkuQuery(value)
                  if (!value.trim()) {
                    setScoringPrepNmId('')
                    setSelectedScoringPrepSku(null)
                  }
                }}
                onSelect={(item) => {
                  setSelectedScoringPrepSku(item)
                  setScoringPrepNmId(String(item.nm_id))
                  setScoringPrepSkuQuery(item.vendor_code ? `${item.vendor_code} · ${item.nm_id}` : String(item.nm_id))
                }}
                placeholder="Найти по nm_id или vendor_code"
              />
            </div>
            <div style={{ color: '#6b7280', fontSize: 13, minHeight: 42, display: 'flex', alignItems: 'center' }}>
              {scoringPrepNmId ? (
                <span>
                  SKU scope: `nm_id = {scoringPrepNmId}`
                  {selectedScoringPrepSku?.title ? ` · ${selectedScoringPrepSku.title}` : ''}
                </span>
              ) : (
                <span>Выберите SKU, чтобы увидеть scoring preparation и actual scoring для cluster profiles.</span>
              )}
            </div>
          </div>
        </div>
      )}

      {activeTab === 'queries' && (
        <>
          <div
            className="card"
            style={{
              padding: 16,
              borderRadius: 12,
              border: '1px solid #e5e7eb',
              background: '#fff',
              marginBottom: 16,
            }}
          >
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Pruning status</div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {STATUS_OPTIONS.map((status) => (
                    <label
                      key={status}
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: 6,
                        padding: '8px 10px',
                        border: '1px solid #d1d5db',
                        borderRadius: 10,
                        cursor: 'pointer',
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={selectedStatuses.has(status)}
                        onChange={() => toggleStatus(status)}
                      />
                      <span>{status}</span>
                    </label>
                  ))}
                </div>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Bucket</label>
                <select
                  value={selectedBucket}
                  onChange={(event) => setSelectedBucket(event.target.value as BucketFilter)}
                  style={{
                    width: '100%',
                    minHeight: 42,
                    borderRadius: 10,
                    border: '1px solid #d1d5db',
                    padding: '0 12px',
                  }}
                >
                  {BUCKET_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Intent</label>
                <select
                  value={selectedIntent}
                  onChange={(event) => setSelectedIntent(event.target.value as IntentFilter)}
                  style={{
                    width: '100%',
                    minHeight: 42,
                    borderRadius: 10,
                    border: '1px solid #d1d5db',
                    padding: '0 12px',
                  }}
                >
                  {INTENT_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Search</label>
                <input
                  type="text"
                  value={searchValue}
                  onChange={(event) => setSearchValue(event.target.value)}
                  placeholder="normalized query text"
                  style={{
                    width: '100%',
                    minHeight: 42,
                    borderRadius: 10,
                    border: '1px solid #d1d5db',
                    padding: '0 12px',
                  }}
                />
              </div>
            </div>
          </div>

          <div
            className="card"
            style={{
              borderRadius: 12,
              border: '1px solid #e5e7eb',
              background: '#fff',
              overflow: 'hidden',
            }}
          >
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 980 }}>
                <thead style={{ background: '#f9fafb' }}>
                  <tr>
                    {['query', 'ranking_value_used', 'bucket', 'pruning_status', 'intent_type', 'cluster_key', 'cluster_label_candidate'].map((label) => (
                      <th
                        key={label}
                        style={{
                          textAlign: 'left',
                          padding: '12px 14px',
                          fontSize: 12,
                          textTransform: 'uppercase',
                          letterSpacing: 0.4,
                          color: '#6b7280',
                          borderBottom: '1px solid #e5e7eb',
                        }}
                      >
                        {label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {loading && !isCurrentViewFresh ? (
                    <tr>
                      <td colSpan={7} style={{ padding: 24, color: '#6b7280' }}>
                        Загрузка queries...
                      </td>
                    </tr>
                  ) : queryRows.length === 0 ? (
                    <tr>
                      <td colSpan={7} style={{ padding: 24, color: '#6b7280' }}>
                        Нет строк для текущих фильтров.
                      </td>
                    </tr>
                  ) : (
                    queryRows.map((item) => (
                      <tr key={`${item.pruning_status}:${item.normalized_query_text}`} style={{ borderBottom: '1px solid #f3f4f6' }}>
                        <td style={{ padding: '14px', fontWeight: 600, color: '#111827' }}>{item.normalized_query_text}</td>
                        <td style={{ padding: '14px', color: '#111827' }}>{formatNumber(item.ranking_value_used)}</td>
                        <td style={{ padding: '14px' }}><BucketBadge value={item.bucket} /></td>
                        <td style={{ padding: '14px' }}><PruningBadge value={item.pruning_status} /></td>
                        <td style={{ padding: '14px' }}><IntentBadge value={item.intent_type} /></td>
                        <td style={{ padding: '14px', fontFamily: 'monospace', fontSize: 13 }}>{item.cluster_key || '—'}</td>
                        <td style={{ padding: '14px', color: '#374151' }}>{item.cluster_label_candidate || '—'}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
            <div style={{ padding: '0 16px 16px' }}>
              <Pagination
                page={queryPagination.page}
                totalPages={queryPagination.total_pages}
                onChange={setQueriesPage}
              />
            </div>
          </div>
        </>
      )}

      {activeTab === 'clusters' && (
        <div
          className="card"
          style={{
            borderRadius: 12,
            border: '1px solid #e5e7eb',
            background: '#fff',
            overflow: 'hidden',
          }}
        >
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 880 }}>
              <thead style={{ background: '#f9fafb' }}>
                <tr>
                  {['cluster_key', 'cluster_label_candidate', 'query_count', 'head', 'mid', 'tail'].map((label) => (
                    <th
                      key={label}
                      style={{
                        textAlign: 'left',
                        padding: '12px 14px',
                        fontSize: 12,
                        textTransform: 'uppercase',
                        letterSpacing: 0.4,
                        color: '#6b7280',
                        borderBottom: '1px solid #e5e7eb',
                      }}
                    >
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {loading && !isCurrentViewFresh ? (
                  <tr>
                    <td colSpan={6} style={{ padding: 24, color: '#6b7280' }}>
                      Загрузка clusters...
                    </td>
                  </tr>
                ) : clusterRows.length === 0 ? (
                  <tr>
                    <td colSpan={6} style={{ padding: 24, color: '#6b7280' }}>
                      Кластеры не найдены для выбранной категории.
                    </td>
                  </tr>
                ) : (
                  clusterRows.map((cluster) => {
                    const isExpanded = expandedClusters.has(cluster.cluster_key)
                    return (
                      <Fragment key={cluster.cluster_key}>
                        <tr
                          onClick={() => toggleClusterRow(cluster.cluster_key)}
                          style={{
                            borderBottom: '1px solid #f3f4f6',
                            cursor: 'pointer',
                            background: isExpanded ? '#fafaf9' : '#fff',
                          }}
                        >
                          <td style={{ padding: '14px', fontFamily: 'monospace', fontSize: 13, color: '#111827' }}>
                            {cluster.cluster_key}
                          </td>
                          <td style={{ padding: '14px', fontWeight: 600, color: '#111827' }}>
                            {cluster.cluster_label_candidate}
                          </td>
                          <td style={{ padding: '14px', color: '#111827' }}>{cluster.query_count}</td>
                          <td style={{ padding: '14px' }}><BucketBadge value="head" /> <span style={{ marginLeft: 8 }}>{cluster.head_query_count}</span></td>
                          <td style={{ padding: '14px' }}><BucketBadge value="mid" /> <span style={{ marginLeft: 8 }}>{cluster.mid_query_count}</span></td>
                          <td style={{ padding: '14px' }}><BucketBadge value="tail" /> <span style={{ marginLeft: 8 }}>{cluster.tail_query_count}</span></td>
                        </tr>
                        {isExpanded && (
                          <tr>
                            <td colSpan={6} style={{ padding: 0, background: '#fafaf9' }}>
                              <div style={{ padding: 16, borderTop: '1px solid #e5e7eb' }}>
                                <div style={{ fontSize: 13, fontWeight: 700, color: '#111827', marginBottom: 12 }}>
                                  Queries inside cluster
                                </div>
                                <div style={{ overflowX: 'auto' }}>
                                  <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 720 }}>
                                    <thead>
                                      <tr>
                                        {['query', 'bucket', 'ranking', 'intent', 'membership_reason_code'].map((label) => (
                                          <th
                                            key={label}
                                            style={{
                                              textAlign: 'left',
                                              padding: '10px 12px',
                                              fontSize: 12,
                                              textTransform: 'uppercase',
                                              color: '#6b7280',
                                              borderBottom: '1px solid #e5e7eb',
                                            }}
                                          >
                                            {label}
                                          </th>
                                        ))}
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {cluster.members.map((member) => (
                                        <tr key={`${cluster.cluster_key}:${member.normalized_query_text}`} style={{ borderBottom: '1px solid #f3f4f6' }}>
                                          <td style={{ padding: '12px', color: '#111827', fontWeight: 600 }}>
                                            {member.normalized_query_text}
                                          </td>
                                          <td style={{ padding: '12px' }}><BucketBadge value={member.bucket} /></td>
                                          <td style={{ padding: '12px', color: '#111827' }}>{formatNumber(member.ranking_value_used)}</td>
                                          <td style={{ padding: '12px' }}><IntentBadge value={member.intent_type} /></td>
                                          <td style={{ padding: '12px', fontFamily: 'monospace', fontSize: 13 }}>
                                            {member.membership_reason_code}
                                          </td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                </div>
                              </div>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>
          <div style={{ padding: '0 16px 16px' }}>
            <Pagination
              page={clusterPagination.page}
              totalPages={clusterPagination.total_pages}
              onChange={setClustersPage}
            />
          </div>
        </div>
      )}

      {activeTab === 'hybrid' && (
        <>
          <div
            className="card"
            style={{
              padding: 16,
              borderRadius: 12,
              border: '1px solid #e5e7eb',
              background: '#fff',
              marginBottom: 16,
            }}
          >
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Provenance</label>
                <select
                  value={selectedHybridProvenance}
                  onChange={(event) => setSelectedHybridProvenance(event.target.value as HybridProvenanceFilter)}
                  style={{
                    width: '100%',
                    minHeight: 42,
                    borderRadius: 10,
                    border: '1px solid #d1d5db',
                    padding: '0 12px',
                  }}
                >
                  {HYBRID_PROVENANCE_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Bucket</label>
                <select
                  value={selectedHybridBucket}
                  onChange={(event) => setSelectedHybridBucket(event.target.value as BucketFilter)}
                  style={{
                    width: '100%',
                    minHeight: 42,
                    borderRadius: 10,
                    border: '1px solid #d1d5db',
                    padding: '0 12px',
                  }}
                >
                  {BUCKET_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Cluster key</label>
                <input
                  type="text"
                  value={hybridClusterKey}
                  onChange={(event) => setHybridClusterKey(event.target.value)}
                  placeholder="exact qcl:v1:..."
                  style={{
                    width: '100%',
                    minHeight: 42,
                    borderRadius: 10,
                    border: '1px solid #d1d5db',
                    padding: '0 12px',
                  }}
                />
              </div>

              <div style={{ display: 'flex', alignItems: 'end', gap: 12, flexWrap: 'wrap' }}>
                <label
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 8,
                    minHeight: 42,
                    padding: '0 4px',
                    fontSize: 14,
                    color: '#111827',
                  }}
                >
                  <input
                    type="checkbox"
                    checked={selectedHybridOnlyAnchors}
                    onChange={(event) => setSelectedHybridOnlyAnchors(event.target.checked)}
                  />
                  Only anchors
                </label>
                <label
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 8,
                    minHeight: 42,
                    padding: '0 4px',
                    fontSize: 14,
                    color: '#111827',
                  }}
                >
                  <input
                    type="checkbox"
                    checked={selectedHybridOnlyFallback}
                    onChange={(event) => setSelectedHybridOnlyFallback(event.target.checked)}
                  />
                  Only fallback
                </label>
              </div>
            </div>
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
              gap: 12,
              marginBottom: 16,
            }}
          >
            {[
              ['Total Processed', hybridDiagnostics?.total_queries_processed || 0],
              ['Individual', hybridDiagnostics?.individual_count || 0],
              ['Cluster Derived', hybridDiagnostics?.cluster_derived_count || 0],
              ['Rejected', hybridDiagnostics?.rejected_count || 0],
              ['Fallback', hybridDiagnostics?.fallback_count || 0],
              ['Versions Created', hybridDiagnostics?.versions_created || 0],
            ].map(([label, value]) => (
              <div
                key={label}
                className="card"
                style={{
                  padding: 16,
                  borderRadius: 12,
                  border: '1px solid #e5e7eb',
                  background: '#fff',
                }}
              >
                <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: 0.4, color: '#6b7280' }}>
                  {label}
                </div>
                <div style={{ marginTop: 8, fontSize: 28, fontWeight: 700, color: '#111827' }}>{value}</div>
              </div>
            ))}
          </div>

          <div
            className="card"
            style={{
              borderRadius: 12,
              border: '1px solid #e5e7eb',
              background: '#fff',
              overflow: 'hidden',
            }}
          >
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 1480 }}>
                <thead style={{ background: '#f9fafb' }}>
                  <tr>
                    {[
                      'query',
                      'bucket',
                      'is_anchor',
                      'cluster_key',
                      'cluster_label_candidate',
                      'cluster_query_count',
                      'provenance',
                      'source_anchor_query',
                      'intent_type',
                      'inheritance_reason',
                    ].map((label) => (
                      <th
                        key={label}
                        style={{
                          textAlign: 'left',
                          padding: '12px 14px',
                          fontSize: 12,
                          textTransform: 'uppercase',
                          letterSpacing: 0.4,
                          color: '#6b7280',
                          borderBottom: '1px solid #e5e7eb',
                        }}
                      >
                        {label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {loading && !isCurrentViewFresh ? (
                    <tr>
                      <td colSpan={10} style={{ padding: 24, color: '#6b7280' }}>
                        Загрузка hybrid...
                      </td>
                    </tr>
                  ) : hybridRows.length === 0 ? (
                    <tr>
                      <td colSpan={10} style={{ padding: 24, color: '#6b7280' }}>
                        Нет строк для текущих hybrid-фильтров.
                      </td>
                    </tr>
                  ) : (
                    hybridRows.map((item) => {
                      const rowKey = `${item.cluster_key || 'no-cluster'}:${item.normalized_query_text}:${item.provenance}`
                      const clusterDetail = item.cluster_key ? hybridClusterDetailsByKey[item.cluster_key] : null
                      const isExpanded = item.cluster_key ? expandedHybridClusters.has(item.cluster_key) : false
                      return (
                        <Fragment key={rowKey}>
                          <tr
                            style={{
                              borderBottom: isExpanded ? 'none' : '1px solid #f3f4f6',
                              background: isExpanded ? '#f9fafb' : '#fff',
                            }}
                          >
                            <td style={{ padding: '14px', fontWeight: 600, color: '#111827' }}>{item.normalized_query_text}</td>
                            <td style={{ padding: '14px' }}><BucketBadge value={item.bucket} /></td>
                            <td style={{ padding: '14px' }}><AnchorBadge value={item.is_anchor} /></td>
                            <td style={{ padding: '14px', fontFamily: 'monospace', fontSize: 13 }}>
                              {item.cluster_key ? (
                                <button
                                  type="button"
                                  onClick={() => toggleHybridClusterRow(item.cluster_key!)}
                                  style={{
                                    padding: 0,
                                    border: 'none',
                                    background: 'transparent',
                                    color: '#2563eb',
                                    cursor: 'pointer',
                                    fontFamily: 'inherit',
                                    fontSize: 13,
                                  }}
                                >
                                  {item.cluster_key}
                                </button>
                              ) : '—'}
                            </td>
                            <td style={{ padding: '14px', color: '#374151' }}>{item.cluster_label_candidate || '—'}</td>
                            <td style={{ padding: '14px', color: '#111827' }}>{item.cluster_query_count ?? '—'}</td>
                            <td style={{ padding: '14px' }}><ProvenanceBadge value={item.provenance} /></td>
                            <td style={{ padding: '14px', color: '#374151' }}>{item.source_anchor_query || '—'}</td>
                            <td style={{ padding: '14px' }}><IntentBadge value={item.intent_type} /></td>
                            <td style={{ padding: '14px', fontFamily: 'monospace', fontSize: 13 }}>
                              {item.inheritance_reason_code}
                            </td>
                          </tr>
                          {isExpanded && clusterDetail && (
                            <tr style={{ borderBottom: '1px solid #e5e7eb', background: '#f9fafb' }}>
                              <td colSpan={10} style={{ padding: 16 }}>
                                <div
                                  style={{
                                    border: '1px solid #e5e7eb',
                                    borderRadius: 12,
                                    background: '#fff',
                                    padding: 16,
                                  }}
                                >
                                  <div
                                    style={{
                                      display: 'grid',
                                      gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
                                      gap: 12,
                                      marginBottom: 16,
                                    }}
                                  >
                                    <div>
                                      <div style={{ fontSize: 12, textTransform: 'uppercase', color: '#6b7280', marginBottom: 6 }}>
                                        Cluster label
                                      </div>
                                      <div style={{ color: '#111827', fontWeight: 600 }}>{clusterDetail.cluster_label_candidate}</div>
                                    </div>
                                    <div>
                                      <div style={{ fontSize: 12, textTransform: 'uppercase', color: '#6b7280', marginBottom: 6 }}>
                                        Cluster size
                                      </div>
                                      <div style={{ color: '#111827', fontWeight: 600 }}>{clusterDetail.query_count}</div>
                                    </div>
                                    <div>
                                      <div style={{ fontSize: 12, textTransform: 'uppercase', color: '#6b7280', marginBottom: 6 }}>
                                        Anchor query
                                      </div>
                                      <div style={{ color: '#111827', fontWeight: 600 }}>{clusterDetail.anchor_query || '—'}</div>
                                    </div>
                                  </div>
                                  <div style={{ overflowX: 'auto' }}>
                                    <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 980 }}>
                                      <thead style={{ background: '#f9fafb' }}>
                                        <tr>
                                          {[
                                            'query',
                                            'bucket',
                                            'is_anchor',
                                            'provenance',
                                            'source_anchor_query',
                                            'intent_type',
                                            'inheritance_reason',
                                          ].map((label) => (
                                            <th
                                              key={label}
                                              style={{
                                                textAlign: 'left',
                                                padding: '10px 12px',
                                                fontSize: 12,
                                                textTransform: 'uppercase',
                                                color: '#6b7280',
                                                borderBottom: '1px solid #e5e7eb',
                                              }}
                                            >
                                              {label}
                                            </th>
                                          ))}
                                        </tr>
                                      </thead>
                                      <tbody>
                                        {clusterDetail.members.map((member) => (
                                          <tr
                                            key={`${clusterDetail.cluster_key}:${member.normalized_query_text}:${member.provenance}`}
                                            style={{ borderBottom: '1px solid #f3f4f6' }}
                                          >
                                            <td style={{ padding: '12px', color: '#111827', fontWeight: 600 }}>
                                              {member.normalized_query_text}
                                            </td>
                                            <td style={{ padding: '12px' }}><BucketBadge value={member.bucket} /></td>
                                            <td style={{ padding: '12px' }}><AnchorBadge value={member.is_anchor} /></td>
                                            <td style={{ padding: '12px' }}><ProvenanceBadge value={member.provenance} /></td>
                                            <td style={{ padding: '12px', color: '#374151' }}>{member.source_anchor_query || '—'}</td>
                                            <td style={{ padding: '12px' }}><IntentBadge value={member.intent_type} /></td>
                                            <td style={{ padding: '12px', fontFamily: 'monospace', fontSize: 13 }}>
                                              {member.inheritance_reason_code}
                                            </td>
                                          </tr>
                                        ))}
                                      </tbody>
                                    </table>
                                  </div>
                                </div>
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      )
                    })
                  )}
                </tbody>
              </table>
            </div>
            <div style={{ padding: '0 16px 16px' }}>
              <Pagination
                page={hybridPagination.page}
                totalPages={hybridPagination.total_pages}
                onChange={setHybridPage}
              />
            </div>
          </div>
        </>
      )}

      {activeTab === 'profiles' && (
        <>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
              gap: 12,
              marginBottom: 16,
            }}
          >
            {[
              ['Profiles Built', profilesDiagnostics?.total_profiles_built || 0],
              ['Strong', profilesDiagnostics?.strong_profiles_count || 0],
              ['Medium', profilesDiagnostics?.medium_profiles_count || 0],
              ['Weak', profilesDiagnostics?.weak_profiles_count || 0],
              ['Empty', profilesDiagnostics?.empty_profiles_count || 0],
              ['Low Confidence', profilesDiagnostics?.profiles_with_low_confidence_count || 0],
            ].map(([label, value]) => (
              <div
                key={label}
                className="card"
                style={{
                  padding: 16,
                  borderRadius: 12,
                  border: '1px solid #e5e7eb',
                  background: '#fff',
                }}
              >
                <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: 0.4, color: '#6b7280' }}>
                  {label}
                </div>
                <div style={{ marginTop: 8, fontSize: 28, fontWeight: 700, color: '#111827' }}>{value}</div>
              </div>
            ))}
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
              gap: 12,
              marginBottom: 16,
            }}
          >
            <AuditStatList
              title="Marker Types"
              items={Object.entries(profilesDiagnostics?.counts_by_marker_type || {}).sort((a, b) => b[1] - a[1])}
            />
            <AuditStatList
              title="Attribute Families"
              items={Object.entries(profilesDiagnostics?.counts_by_attribute_family || {}).sort((a, b) => b[1] - a[1])}
            />
            <AuditStatList
              title="Profile Issues"
              items={[
                ['conflicting markers', profilesDiagnostics?.profiles_with_conflicts_count || 0],
                ['low confidence', profilesDiagnostics?.profiles_with_low_confidence_count || 0],
              ]}
            />
          </div>

          <div
            className="card"
            style={{
              borderRadius: 12,
              border: '1px solid #e5e7eb',
              background: '#fff',
              overflow: 'hidden',
            }}
          >
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 1680 }}>
                <thead style={{ background: '#f9fafb' }}>
                  <tr>
                    {[
                      'cluster_key',
                      'profile_label_candidate',
                      'strength',
                      'confidence',
                      'product_type_markers',
                      'use_case_markers',
                      'attribute_markers',
                      'source_anchor_query',
                      'source_examples',
                    ].map((label) => (
                      <th
                        key={label}
                        style={{
                          textAlign: 'left',
                          padding: '12px 14px',
                          fontSize: 12,
                          textTransform: 'uppercase',
                          letterSpacing: 0.4,
                          color: '#6b7280',
                          borderBottom: '1px solid #e5e7eb',
                        }}
                      >
                        {label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {loading && !isCurrentViewFresh ? (
                    <tr>
                      <td colSpan={9} style={{ padding: 24, color: '#6b7280' }}>
                        Загрузка profiles...
                      </td>
                    </tr>
                  ) : profileRows.length === 0 ? (
                    <tr>
                      <td colSpan={9} style={{ padding: 24, color: '#6b7280' }}>
                        Нет profiles для текущего scope.
                      </td>
                    </tr>
                  ) : (
                    profileRows.map((item) => {
                      const isExpanded = expandedProfiles.has(item.cluster_key)
                      return (
                        <Fragment key={item.cluster_key}>
                          <tr
                            style={{
                              borderBottom: isExpanded ? 'none' : '1px solid #f3f4f6',
                              background: isExpanded ? '#f9fafb' : '#fff',
                            }}
                          >
                            <td style={{ padding: '14px', fontFamily: 'monospace', fontSize: 13 }}>
                              <button
                                type="button"
                                onClick={() => toggleProfileRow(item.cluster_key)}
                                style={{
                                  padding: 0,
                                  border: 'none',
                                  background: 'transparent',
                                  color: '#2563eb',
                                  cursor: 'pointer',
                                  fontFamily: 'inherit',
                                  fontSize: 13,
                                }}
                              >
                                {item.cluster_key}
                              </button>
                            </td>
                            <td style={{ padding: '14px', fontWeight: 600, color: '#111827' }}>{item.profile_label_candidate}</td>
                            <td style={{ padding: '14px' }}><ProfileStrengthBadge value={item.profile_strength} /></td>
                            <td style={{ padding: '14px', color: '#111827' }}>{formatNumber(item.profile_confidence)}</td>
                            <td style={{ padding: '14px', color: '#374151' }}>{formatProfileMarkers(item.product_type_markers)}</td>
                            <td style={{ padding: '14px', color: '#374151' }}>{formatProfileMarkers(item.use_case_markers)}</td>
                            <td style={{ padding: '14px', color: '#374151' }}>{formatProfileMarkers(item.attribute_markers)}</td>
                            <td style={{ padding: '14px', color: '#374151' }}>{item.source_anchor_query || '—'}</td>
                            <td style={{ padding: '14px', color: '#6b7280', fontSize: 13 }}>
                              {item.source_query_examples.length > 0 ? item.source_query_examples.slice(0, 3).join(', ') : '—'}
                            </td>
                          </tr>
                          {isExpanded && (
                            <tr style={{ borderBottom: '1px solid #e5e7eb', background: '#f9fafb' }}>
                              <td colSpan={9} style={{ padding: 16 }}>
                                <div
                                  style={{
                                    border: '1px solid #e5e7eb',
                                    borderRadius: 12,
                                    background: '#fff',
                                    padding: 16,
                                  }}
                                >
                                  <div
                                    style={{
                                      display: 'grid',
                                      gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
                                      gap: 12,
                                      marginBottom: 16,
                                    }}
                                  >
                                    <div>
                                      <div style={{ fontSize: 12, textTransform: 'uppercase', color: '#6b7280', marginBottom: 6 }}>
                                        Query count
                                      </div>
                                      <div style={{ color: '#111827', fontWeight: 600 }}>{item.query_count}</div>
                                    </div>
                                    <div>
                                      <div style={{ fontSize: 12, textTransform: 'uppercase', color: '#6b7280', marginBottom: 6 }}>
                                        Evidence queries
                                      </div>
                                      <div style={{ color: '#111827', fontWeight: 600 }}>{item.evidence_query_count}</div>
                                    </div>
                                    <div>
                                      <div style={{ fontSize: 12, textTransform: 'uppercase', color: '#6b7280', marginBottom: 6 }}>
                                        Weighted signal
                                      </div>
                                      <div style={{ color: '#111827', fontWeight: 600 }}>{formatNumber(item.weighted_signal)}</div>
                                    </div>
                                    <div>
                                      <div style={{ fontSize: 12, textTransform: 'uppercase', color: '#6b7280', marginBottom: 6 }}>
                                        Flags
                                      </div>
                                      <div style={{ color: '#111827', fontWeight: 600 }}>
                                        {item.quality_flags.length > 0 ? item.quality_flags.join(', ') : '—'}
                                      </div>
                                    </div>
                                  </div>

                                  <div
                                    style={{
                                      display: 'grid',
                                      gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                                      gap: 12,
                                      marginBottom: 16,
                                    }}
                                  >
                                    <AuditStatList
                                      title="Product Type Markers"
                                      items={item.product_type_markers.map((marker) => [
                                        marker.value,
                                        `${formatNumber(marker.support_share)} / ${formatNumber(marker.weighted_support)}`,
                                      ])}
                                    />
                                    <AuditStatList
                                      title="Use Case Markers"
                                      items={item.use_case_markers.map((marker) => [
                                        marker.value,
                                        `${formatNumber(marker.support_share)} / ${formatNumber(marker.weighted_support)}`,
                                      ])}
                                    />
                                    <AuditStatList
                                      title="Attribute Markers"
                                      items={item.attribute_markers.map((marker) => [
                                        marker.family ? `${marker.value} (${marker.family})` : marker.value,
                                        `${formatNumber(marker.support_share)} / ${formatNumber(marker.weighted_support)}`,
                                      ])}
                                    />
                                  </div>

                                  <div
                                    style={{
                                      display: 'grid',
                                      gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                                      gap: 12,
                                    }}
                                  >
                                    <AuditStatList
                                      title="Confidence Factors"
                                      items={Object.entries(item.confidence_factors || {}).map(([key, value]) => [key, String(value)])}
                                    />
                                    <AuditStatList
                                      title="Marker Decisions"
                                      items={item.marker_decisions.slice(0, 12).map((decision) => [
                                        `${decision.slot}:${decision.normalized_value}`,
                                        formatMarkerDecision(decision),
                                      ])}
                                    />
                                    <AuditStatList
                                      title="Conflicting Families"
                                      items={item.conflicting_attribute_families.map((family) => [family, 1])}
                                    />
                                    <AuditStatList
                                      title="Source Examples"
                                      items={item.source_query_examples.map((query, index) => [`#${index + 1}`, query])}
                                    />
                                  </div>
                                </div>
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      )
                    })
                  )}
                </tbody>
              </table>
            </div>
            <div style={{ padding: '0 16px 16px' }}>
              <Pagination
                page={profilePagination.page}
                totalPages={profilePagination.total_pages}
                onChange={setProfilesPage}
              />
            </div>
          </div>
        </>
      )}

      {activeTab === 'scoring_prep' && (
        <>
          {!scoringPrepNmId ? (
            <div
              className="card"
              style={{
                padding: 24,
                borderRadius: 12,
                border: '1px solid #e5e7eb',
                background: '#fff',
                color: '#6b7280',
              }}
            >
              Выберите SKU через lookup выше, чтобы загрузить scoring preparation.
            </div>
          ) : (
            <>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                  gap: 12,
                  marginBottom: 16,
                }}
              >
                {[
                  ['Comparisons', scoringPrepDiagnostics?.total_cluster_comparisons || 0],
                  ['Ready', scoringPrepDiagnostics?.ready_count || 0],
                  ['Partial', scoringPrepDiagnostics?.partial_count || 0],
                  ['Poor', scoringPrepDiagnostics?.poor_count || 0],
                  ['Weak Profiles', scoringPrepDiagnostics?.weak_profile_count || 0],
                  ['Missing Product Type', scoringPrepDiagnostics?.missing_product_type_count || 0],
                ].map(([label, value]) => (
                  <div
                    key={label}
                    className="card"
                    style={{
                      padding: 16,
                      borderRadius: 12,
                      border: '1px solid #e5e7eb',
                      background: '#fff',
                    }}
                  >
                    <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: 0.4, color: '#6b7280' }}>
                      {label}
                    </div>
                    <div style={{ marginTop: 8, fontSize: 28, fontWeight: 700, color: '#111827' }}>{value}</div>
                  </div>
                ))}
              </div>

              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
                  gap: 12,
                  marginBottom: 16,
                }}
              >
                <AuditStatList
                  title="Match Rates"
                  items={[
                    ['product_type matched', formatNumber((scoringPrepDiagnostics?.product_type_matched_rate || 0) * 100)],
                    ['use_case matched', formatNumber((scoringPrepDiagnostics?.use_case_matched_rate || 0) * 100)],
                    ['attribute matched', formatNumber((scoringPrepDiagnostics?.attribute_matched_rate || 0) * 100)],
                  ]}
                />
                <AuditStatList
                  title="Data Gaps"
                  items={[
                    ['insufficient sku data', scoringPrepDiagnostics?.insufficient_sku_data_count || 0],
                    ['selected nm_id', scoringPrepDiagnostics?.nm_id || 0],
                  ]}
                />
              </div>

              <div
                className="card"
                style={{
                  borderRadius: 12,
                  border: '1px solid #e5e7eb',
                  background: '#fff',
                  overflow: 'hidden',
                }}
              >
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 1480 }}>
                    <thead style={{ background: '#f9fafb' }}>
                      <tr>
                        {[
                          'cluster_key',
                          'profile_label_candidate',
                          'product_type_match',
                          'use_case',
                          'attribute',
                          'readiness',
                          'flags',
                          'evidence_fields',
                        ].map((label) => (
                          <th
                            key={label}
                            style={{
                              textAlign: 'left',
                              padding: '12px 14px',
                              fontSize: 12,
                              textTransform: 'uppercase',
                              letterSpacing: 0.4,
                              color: '#6b7280',
                              borderBottom: '1px solid #e5e7eb',
                            }}
                          >
                            {label}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {loading && !isCurrentViewFresh ? (
                        <tr>
                          <td colSpan={8} style={{ padding: 24, color: '#6b7280' }}>
                            Загрузка scoring prep...
                          </td>
                        </tr>
                      ) : scoringPrepRows.length === 0 ? (
                        <tr>
                          <td colSpan={8} style={{ padding: 24, color: '#6b7280' }}>
                            Нет preparation rows для текущего SKU.
                          </td>
                        </tr>
                      ) : (
                        scoringPrepRows.map((item) => {
                          const isExpanded = expandedProfiles.has(item.cluster_key)
                          return (
                            <Fragment key={`scoring-prep:${item.cluster_key}`}>
                              <tr
                                style={{
                                  borderBottom: isExpanded ? 'none' : '1px solid #f3f4f6',
                                  background: isExpanded ? '#f9fafb' : '#fff',
                                }}
                              >
                                <td style={{ padding: '14px', fontFamily: 'monospace', fontSize: 13 }}>
                                  <button
                                    type="button"
                                    onClick={() => toggleProfileRow(item.cluster_key)}
                                    style={{
                                      padding: 0,
                                      border: 'none',
                                      background: 'transparent',
                                      color: '#2563eb',
                                      cursor: 'pointer',
                                      fontFamily: 'inherit',
                                      fontSize: 13,
                                    }}
                                  >
                                    {item.cluster_key}
                                  </button>
                                </td>
                                <td style={{ padding: '14px', fontWeight: 600, color: '#111827' }}>
                                  {item.profile_label_candidate || '—'}
                                </td>
                                <td style={{ padding: '14px' }}><ProductTypeMatchBadge value={item.product_type_match.status} /></td>
                                <td style={{ padding: '14px', color: '#374151' }}>{formatScoringPrepSummary(item.use_case_match)}</td>
                                <td style={{ padding: '14px', color: '#374151' }}>{formatScoringPrepSummary(item.attribute_match)}</td>
                                <td style={{ padding: '14px' }}><ReadinessBadge value={item.readiness_for_scoring} /></td>
                                <td style={{ padding: '14px', color: '#374151' }}>{formatScoringPrepFlags(item.preparation_flags)}</td>
                                <td style={{ padding: '14px', color: '#374151', fontSize: 13 }}>{formatEvidenceFields(item.sku_evidence_summary)}</td>
                              </tr>
                              {isExpanded && (
                                <tr style={{ borderBottom: '1px solid #e5e7eb', background: '#f9fafb' }}>
                                  <td colSpan={8} style={{ padding: 16 }}>
                                    <div
                                      style={{
                                        border: '1px solid #e5e7eb',
                                        borderRadius: 12,
                                        background: '#fff',
                                        padding: 16,
                                      }}
                                    >
                                      <div
                                        style={{
                                          display: 'grid',
                                          gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
                                          gap: 12,
                                          marginBottom: 16,
                                        }}
                                      >
                                        <AuditStatList
                                          title="Product Type"
                                          items={[
                                            ['status', item.product_type_match.status],
                                            ['reason', item.product_type_match.reason || '—'],
                                            ['evidence', item.product_type_match.evidence.join(' | ') || '—'],
                                          ]}
                                        />
                                        <AuditStatList
                                          title="Use Case"
                                          items={[
                                            ['reason', item.use_case_match.reason || '—'],
                                            ['matched', item.use_case_match.matched_markers.length],
                                            ['missed', item.use_case_match.missed_markers.length],
                                            ['unknown', item.use_case_match.unknown_markers.length],
                                          ]}
                                        />
                                        <AuditStatList
                                          title="Attribute"
                                          items={[
                                            ['reason', item.attribute_match.reason || '—'],
                                            ['matched', item.attribute_match.matched_markers.length],
                                            ['conflicting', item.attribute_match.conflicting_markers.length],
                                            ['missed', item.attribute_match.missed_markers.length],
                                            ['unknown', item.attribute_match.unknown_markers.length],
                                          ]}
                                        />
                                        <AuditStatList
                                          title="Evidence Summary"
                                          items={[
                                            ['title present', String(item.sku_evidence_summary.title_present)],
                                            ['attributes present', String(item.sku_evidence_summary.attributes_present)],
                                            ['description present', String(item.sku_evidence_summary.description_present)],
                                          ]}
                                        />
                                      </div>

                                      <div
                                        style={{
                                          display: 'grid',
                                          gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                                          gap: 12,
                                        }}
                                      >
                                        <AuditStatList
                                          title="Product Type Markers"
                                          items={item.product_type_match.marker_evaluations.map((marker) => [
                                            marker.normalized_value,
                                            formatScoringPrepMarker(marker),
                                          ])}
                                        />
                                        <AuditStatList
                                          title="Use Case Markers"
                                          items={[
                                            ...item.use_case_match.matched_markers,
                                            ...item.use_case_match.missed_markers,
                                            ...item.use_case_match.unknown_markers,
                                          ].map((marker) => [marker.normalized_value, formatScoringPrepMarker(marker)])}
                                        />
                                        <AuditStatList
                                          title="Attribute Markers"
                                          items={[
                                            ...item.attribute_match.matched_markers,
                                            ...item.attribute_match.conflicting_markers,
                                            ...item.attribute_match.missed_markers,
                                            ...item.attribute_match.unknown_markers,
                                          ].map((marker) => [marker.normalized_value, formatScoringPrepMarker(marker)])}
                                        />
                                      </div>
                                    </div>
                                  </td>
                                </tr>
                              )}
                            </Fragment>
                          )
                        })
                      )}
                    </tbody>
                  </table>
                </div>
                <div style={{ padding: '0 16px 16px' }}>
                  <Pagination
                    page={scoringPrepPagination.page}
                    totalPages={scoringPrepPagination.total_pages}
                    onChange={setScoringPrepPage}
                  />
                </div>
              </div>
            </>
          )}
        </>
      )}

      {activeTab === 'scoring' && (
        <>
          {!scoringPrepNmId ? (
            <div
              className="card"
              style={{
                padding: 24,
                borderRadius: 12,
                border: '1px solid #e5e7eb',
                background: '#fff',
                color: '#6b7280',
              }}
            >
              Выберите SKU через lookup выше, чтобы загрузить actual scoring.
            </div>
          ) : (
            <>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                  gap: 12,
                  marginBottom: 16,
                }}
              >
                {[
                  ['Scored Clusters', actualScoringDiagnostics?.total_clusters_scored || 0],
                  ['Avg Score', actualScoringDiagnostics?.avg_score || 0],
                  ['Top Score', actualScoringDiagnostics?.top_score || 0],
                  ['Bottom Score', actualScoringDiagnostics?.bottom_score || 0],
                  ['Positive %', (actualScoringDiagnostics?.positive_score_share || 0) * 100],
                  ['Negative %', (actualScoringDiagnostics?.negative_score_share || 0) * 100],
                ].map(([label, value]) => (
                  <div
                    key={label}
                    className="card"
                    style={{
                      padding: 16,
                      borderRadius: 12,
                      border: '1px solid #e5e7eb',
                      background: '#fff',
                    }}
                  >
                    <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: 0.4, color: '#6b7280' }}>
                      {label}
                    </div>
                    <div style={{ marginTop: 8, fontSize: 28, fontWeight: 700, color: '#111827' }}>
                      {formatNumber(value)}
                    </div>
                  </div>
                ))}
              </div>

              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
                  gap: 12,
                  marginBottom: 16,
                }}
              >
                <AuditStatList
                  title="Distribution"
                  items={[
                    ['positive (>0)', formatNumber((actualScoringDiagnostics?.positive_score_share || 0) * 100)],
                    ['neutral (-0.2..0.2)', formatNumber((actualScoringDiagnostics?.neutral_score_share || 0) * 100)],
                    ['negative (<0)', formatNumber((actualScoringDiagnostics?.negative_score_share || 0) * 100)],
                  ]}
                />
                <AuditStatList
                  title="Avg Contributions"
                  items={[
                    ['product_type', actualScoringDiagnostics?.avg_product_type_score || 0],
                    ['use_case', actualScoringDiagnostics?.avg_use_case_score || 0],
                    ['attribute', actualScoringDiagnostics?.avg_attribute_score || 0],
                  ]}
                />
              </div>

              <div
                className="card"
                style={{
                  borderRadius: 12,
                  border: '1px solid #e5e7eb',
                  background: '#fff',
                  overflow: 'hidden',
                }}
              >
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 1280 }}>
                    <thead style={{ background: '#f9fafb' }}>
                      <tr>
                        {[
                          'cluster_key',
                          'label',
                          'final_score',
                          'breakdown',
                          'readiness',
                          'flags',
                          'penalties',
                        ].map((label) => (
                          <th
                            key={label}
                            style={{
                              textAlign: 'left',
                              padding: '12px 14px',
                              fontSize: 12,
                              textTransform: 'uppercase',
                              letterSpacing: 0.4,
                              color: '#6b7280',
                              borderBottom: '1px solid #e5e7eb',
                            }}
                          >
                            {label}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {loading && !isCurrentViewFresh ? (
                        <tr>
                          <td colSpan={7} style={{ padding: 24, color: '#6b7280' }}>
                            Загрузка scoring...
                          </td>
                        </tr>
                      ) : actualScoringRows.length === 0 ? (
                        <tr>
                          <td colSpan={7} style={{ padding: 24, color: '#6b7280' }}>
                            Нет scored clusters для текущего SKU.
                          </td>
                        </tr>
                      ) : (
                        actualScoringRows.map((item) => {
                          const isExpanded = expandedProfiles.has(item.cluster_key)
                          return (
                            <Fragment key={`actual-scoring:${item.cluster_key}`}>
                              <tr
                                style={{
                                  borderBottom: isExpanded ? 'none' : '1px solid #f3f4f6',
                                  background: isExpanded ? '#f9fafb' : '#fff',
                                }}
                              >
                                <td style={{ padding: '14px', fontFamily: 'monospace', fontSize: 13 }}>
                                  <button
                                    type="button"
                                    onClick={() => toggleProfileRow(item.cluster_key)}
                                    style={{
                                      padding: 0,
                                      border: 'none',
                                      background: 'transparent',
                                      color: '#2563eb',
                                      cursor: 'pointer',
                                      fontFamily: 'inherit',
                                      fontSize: 13,
                                    }}
                                  >
                                    {item.cluster_key}
                                  </button>
                                </td>
                                <td style={{ padding: '14px', fontWeight: 600, color: '#111827' }}>
                                  {item.profile_label_candidate || '—'}
                                </td>
                                <td style={{ padding: '14px', color: '#111827', fontWeight: 700 }}>
                                  {formatNumber(item.final_score)}
                                </td>
                                <td style={{ padding: '14px', color: '#374151' }}>{formatActualScoreBreakdown(item)}</td>
                                <td style={{ padding: '14px' }}><ReadinessBadge value={item.readiness_for_scoring} /></td>
                                <td style={{ padding: '14px', color: '#374151' }}>{formatScoringPrepFlags(item.preparation_flags)}</td>
                                <td style={{ padding: '14px', color: '#374151' }}>{formatActualPenalties(item)}</td>
                              </tr>
                              {isExpanded && (
                                <tr style={{ borderBottom: '1px solid #e5e7eb', background: '#f9fafb' }}>
                                  <td colSpan={7} style={{ padding: 16 }}>
                                    <div
                                      style={{
                                        border: '1px solid #e5e7eb',
                                        borderRadius: 12,
                                        background: '#fff',
                                        padding: 16,
                                      }}
                                    >
                                      <div
                                        style={{
                                          display: 'grid',
                                          gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
                                          gap: 12,
                                          marginBottom: 16,
                                        }}
                                      >
                                        <AuditStatList
                                          title="Score Breakdown"
                                          items={[
                                            ['final_score', item.final_score],
                                            ['base_score', item.base_score],
                                            ['weighted_score', item.weighted_score],
                                            ['penalties_total', item.penalties_total],
                                          ]}
                                        />
                                        <AuditStatList
                                          title="Components"
                                          items={[
                                            ['product_type', item.product_type_score],
                                            ['use_case', item.use_case_score],
                                            ['attribute', item.attribute_score],
                                          ]}
                                        />
                                        <AuditStatList
                                          title="Modifiers"
                                          items={[
                                            ['profile_strength', `${item.modifiers.profile_strength} × ${item.modifiers.profile_strength_multiplier}`],
                                            ['readiness', `${item.modifiers.readiness_for_scoring} × ${item.modifiers.readiness_multiplier}`],
                                            ['combined', item.modifiers.combined_multiplier],
                                          ]}
                                        />
                                        <AuditStatList
                                          title="Penalties"
                                          items={item.penalties.length > 0
                                            ? item.penalties.map((penalty) => [penalty.name, penalty.value])
                                            : [['none', 0]]}
                                        />
                                      </div>
                                      <div
                                        style={{
                                          padding: 14,
                                          borderRadius: 10,
                                          border: '1px solid #e5e7eb',
                                          background: '#f9fafb',
                                          color: '#374151',
                                          lineHeight: 1.5,
                                        }}
                                      >
                                        {item.final_reason || '—'}
                                      </div>
                                    </div>
                                  </td>
                                </tr>
                              )}
                            </Fragment>
                          )
                        })
                      )}
                    </tbody>
                  </table>
                </div>
                <div style={{ padding: '0 16px 16px' }}>
                  <Pagination
                    page={actualScoringPagination.page}
                    totalPages={actualScoringPagination.total_pages}
                    onChange={setActualScoringPage}
                  />
                </div>
              </div>
            </>
          )}
        </>
      )}

      {activeTab === 'audit' && (
        <>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
              gap: 12,
              marginBottom: 16,
            }}
          >
            <AuditStatList
              title="Pruning Reasons"
              items={Object.entries(auditData?.counts_by_pruning_reason_code || {}).sort((a, b) => b[1] - a[1])}
            />
            <AuditStatList
              title="Intent Distribution"
              items={Object.entries(auditData?.query_distribution_by_intent_type || {}).sort((a, b) => b[1] - a[1])}
            />
            <AuditStatList
              title="Bucket Distribution"
              items={Object.entries(auditData?.query_distribution_by_bucket || {}).sort((a, b) => b[1] - a[1])}
            />
            <AuditStatList
              title="Cluster Size Distribution"
              items={Object.entries(auditData?.cluster_size_distribution || {})}
            />
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
              gap: 12,
              marginBottom: 16,
            }}
          >
            <AuditStatList
              title="Kept Candidate Flags"
              items={[
                ['navigation_candidate kept', auditData?.kept_with_navigation_flag_count || 0],
                ['informational_candidate kept', auditData?.kept_with_informational_flag_count || 0],
                ['garbage_candidate kept', auditData?.kept_with_garbage_flag_count || 0],
                ['two-member clusters', auditData?.two_member_cluster_count || 0],
              ]}
            />
            <AuditStatList
              title="Kept Preparation Flags"
              items={Object.entries(auditData?.kept_flag_counts || {}).sort((a, b) => b[1] - a[1])}
            />
            <AuditStatList
              title="Suspicious Keep Issues"
              items={Object.entries(auditData?.suspicious_kept_issue_counts || {}).sort((a, b) => b[1] - a[1])}
            />
            <AuditStatList
              title="Intent x Bucket"
              items={Object.entries(auditData?.query_distribution_by_intent_and_bucket || {}).map(([intent, counts]) => [
                intent,
                `${counts.head || 0}/${counts.mid || 0}/${counts.tail || 0}`,
              ])}
            />
          </div>

          {loading && !isCurrentViewFresh ? (
            <div
              className="card"
              style={{
                padding: 24,
                borderRadius: 12,
                border: '1px solid #e5e7eb',
                background: '#fff',
                color: '#6b7280',
              }}
            >
              Загрузка audit...
            </div>
          ) : (
            <div style={{ display: 'grid', gap: 16 }}>
              {auditData?.lexical_tightening && (
                <>
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
                      gap: 12,
                    }}
                  >
                    <AuditStatList
                      title="Legacy Lexical"
                      items={[
                        ['clusters', auditData.lexical_tightening.legacy_metrics.total_clusters],
                        ['singletons', auditData.lexical_tightening.legacy_metrics.singleton_clusters],
                        ['two-member', auditData.lexical_tightening.legacy_metrics.two_member_clusters],
                        ['biggest cluster', auditData.lexical_tightening.legacy_metrics.biggest_cluster_size],
                        ['suspicious keeps', auditData.lexical_tightening.legacy_metrics.suspicious_keep_count],
                      ]}
                    />
                    <AuditStatList
                      title="Tightened Lexical"
                      items={[
                        ['clusters', auditData.lexical_tightening.tightened_metrics.total_clusters],
                        ['singletons', auditData.lexical_tightening.tightened_metrics.singleton_clusters],
                        ['two-member', auditData.lexical_tightening.tightened_metrics.two_member_clusters],
                        ['biggest cluster', auditData.lexical_tightening.tightened_metrics.biggest_cluster_size],
                        ['suspicious keeps', auditData.lexical_tightening.tightened_metrics.suspicious_keep_count],
                      ]}
                    />
                    <AuditStatList
                      title="Lexical Improvement"
                      items={[
                        [
                          'biggest cluster reduction',
                          auditData.lexical_tightening.legacy_metrics.biggest_cluster_size -
                            auditData.lexical_tightening.tightened_metrics.biggest_cluster_size,
                        ],
                        [
                          'singleton delta',
                          auditData.lexical_tightening.tightened_metrics.singleton_clusters -
                            auditData.lexical_tightening.legacy_metrics.singleton_clusters,
                        ],
                        [
                          'two-member delta',
                          auditData.lexical_tightening.tightened_metrics.two_member_clusters -
                            auditData.lexical_tightening.legacy_metrics.two_member_clusters,
                        ],
                        [
                          'suspicious keep delta',
                          auditData.lexical_tightening.tightened_metrics.suspicious_keep_count -
                            auditData.lexical_tightening.legacy_metrics.suspicious_keep_count,
                        ],
                      ]}
                    />
                  </div>
                  <LexicalImprovementTable rows={auditData.lexical_tightening.improved_query_cases || []} />
                  <AuditClusterTable
                    title="Legacy Biggest Clusters"
                    rows={auditData.lexical_tightening.legacy_top_biggest_clusters || []}
                  />
                  <AuditClusterTable
                    title="Tightened Biggest Clusters"
                    rows={auditData.lexical_tightening.tightened_top_biggest_clusters || []}
                  />
                  <AuditClusterPairTable
                    title="Legacy Near-Duplicate Cluster Pairs"
                    rows={auditData.lexical_tightening.legacy_top_near_duplicate_clusters || []}
                  />
                  <AuditClusterPairTable
                    title="Tightened Near-Duplicate Cluster Pairs"
                    rows={auditData.lexical_tightening.tightened_top_near_duplicate_clusters || []}
                  />
                </>
              )}
              <AuditQueryTable
                title="Top Suspicious Kept Queries"
                rows={auditData?.top_suspicious_kept_queries || []}
              />
              <AuditQueryTable
                title="Top Review Queries"
                rows={auditData?.top_review_queries || []}
              />
              <AuditClusterTable
                title="Top Biggest Clusters"
                rows={auditData?.top_biggest_clusters || []}
              />
              <AuditClusterTable
                title="Top Singleton Clusters By Ranking"
                rows={auditData?.top_singleton_clusters_by_ranking || []}
              />
              <AuditClusterTable
                title="Top Small High-Ranking Clusters"
                rows={auditData?.top_small_high_ranking_clusters || []}
              />
              <AuditClusterTable
                title="Top Generic Label Clusters"
                rows={auditData?.top_generic_label_clusters || []}
              />
              <AuditClusterPairTable
                title="Top Near-Duplicate Cluster Pairs"
                rows={auditData?.top_near_duplicate_clusters || []}
              />
            </div>
          )}
        </>
      )}

      {activeTab === 'compare' && (
        <>
          <div
            className="card"
            style={{
              padding: 16,
              borderRadius: 12,
              border: '1px solid #e5e7eb',
              background: '#fff',
              marginBottom: 16,
            }}
          >
            <div style={{ display: 'grid', gridTemplateColumns: 'minmax(240px, 360px)', gap: 12 }}>
              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 8 }}>
                  Gating Strategy
                </label>
                <select
                  value={selectedSemanticStrategy}
                  onChange={(event) => setSelectedSemanticStrategy(event.target.value)}
                  style={{
                    width: '100%',
                    minHeight: 42,
                    borderRadius: 10,
                    border: '1px solid #d1d5db',
                    padding: '0 12px',
                    background: '#fff',
                  }}
                >
                  {Object.entries(compareData?.available_strategies || {
                    [DEFAULT_SEMANTIC_STRATEGY]: 'Anchor + Family Gate',
                  }).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
              gap: 12,
              marginBottom: 16,
            }}
          >
            <AuditStatList
              title="Lexical Baseline"
              items={[
                ['clusters', compareData?.lexical_summary?.total_clusters || 0],
                ['singletons', compareData?.lexical_summary?.singleton_cluster_count || 0],
                ['avg cluster size', compareData?.lexical_summary?.average_cluster_size || '0'],
                ['biggest cluster', compareData?.lexical_summary?.biggest_cluster_size || 0],
              ]}
            />
            <AuditStatList
              title="Raw Semantic"
              items={[
                ['input queries', compareData?.raw_semantic?.total_input_queries || 0],
                ['clusters', compareData?.raw_semantic?.total_semantic_clusters || 0],
                ['singleton/noise', compareData?.raw_semantic?.singleton_noise_count || 0],
                ['avg cluster size', compareData?.raw_semantic?.average_cluster_size || '0'],
                ['biggest cluster', compareData?.raw_semantic?.biggest_cluster_size || 0],
                ['segments', compareData?.raw_semantic?.segment_count || 0],
              ]}
            />
            <AuditStatList
              title="Gated Semantic"
              items={[
                ['strategy', compareData?.gated_semantic?.strategy_label || '—'],
                ['clusters', compareData?.gated_semantic?.total_semantic_clusters || 0],
                ['singleton/noise', compareData?.gated_semantic?.singleton_noise_count || 0],
                ['avg cluster size', compareData?.gated_semantic?.average_cluster_size || '0'],
                ['biggest cluster', compareData?.gated_semantic?.biggest_cluster_size || 0],
                ['segments', compareData?.gated_semantic?.segment_count || 0],
              ]}
            />
            <AuditStatList
              title="Improvement"
              items={[
                ['biggest cluster reduction', compareData?.improvement_summary?.biggest_cluster_reduction || 0],
                ['raw biggest cluster', compareData?.improvement_summary?.raw_biggest_cluster_size || 0],
                ['gated biggest cluster', compareData?.improvement_summary?.gated_biggest_cluster_size || 0],
                ['raw total clusters', compareData?.improvement_summary?.raw_total_clusters || 0],
                ['gated total clusters', compareData?.improvement_summary?.gated_total_clusters || 0],
                ['raw singleton/noise', compareData?.improvement_summary?.raw_singleton_noise_count || 0],
                ['gated singleton/noise', compareData?.improvement_summary?.gated_singleton_noise_count || 0],
              ]}
            />
          </div>

          {loading && !isCurrentViewFresh ? (
            <div
              className="card"
              style={{
                padding: 24,
                borderRadius: 12,
                border: '1px solid #e5e7eb',
                background: '#fff',
                color: '#6b7280',
              }}
            >
              Загрузка semantic comparison...
            </div>
          ) : (
            <div style={{ display: 'grid', gap: 16 }}>
              <CompareClusterTable
                title="Top Biggest Lexical Clusters"
                rows={compareData?.raw_comparison?.top_lexical_clusters || []}
              />
              <CompareClusterTable
                title="Top Biggest Raw Semantic Clusters"
                rows={compareData?.raw_semantic?.top_semantic_clusters || []}
              />
              <CompareCaseTable
                title="Raw Semantic Over-Broad Cases"
                rows={compareData?.raw_comparison?.semantic_overbroad_cases || []}
                mode="overbroad"
              />
              <CompareCaseTable
                title="Raw Semantic Grouped Lexical Fragments"
                rows={compareData?.raw_comparison?.semantic_grouped_fragment_cases || []}
                mode="grouped"
              />
              <AuditStatList
                title="Raw Semantic Cluster Size Distribution"
                items={Object.entries(compareData?.raw_semantic?.cluster_size_distribution || {})}
              />
              <CompareClusterTable
                title="Top Biggest Gated Semantic Clusters"
                rows={compareData?.gated_semantic?.top_semantic_clusters || []}
              />
              <CompareCaseTable
                title="Gated Semantic Over-Broad Cases"
                rows={compareData?.gated_comparison?.semantic_overbroad_cases || []}
                mode="overbroad"
              />
              <CompareCaseTable
                title="Gated Semantic Grouped Lexical Fragments"
                rows={compareData?.gated_comparison?.semantic_grouped_fragment_cases || []}
                mode="grouped"
              />
              <AuditStatList
                title="Gated Semantic Cluster Size Distribution"
                items={Object.entries(compareData?.gated_semantic?.cluster_size_distribution || {})}
              />
              <AuditStatList
                title="Gated Top Segments"
                items={(compareData?.gated_semantic?.top_segments || []).map((item) => [
                  item.segment_key,
                  item.query_count,
                ])}
              />
              <AuditQueryTable
                title="Raw Semantic Noise Samples"
                rows={(compareData?.raw_semantic?.sample_noise_queries || []).map((item) => ({
                  normalized_query_text: item.normalized_query_text,
                  display_query: item.display_query,
                  ranking_value_used: item.ranking_value_used,
                  query_type: item.query_type,
                  intent_type: item.intent_type,
                  pruning_status: 'keep',
                  pruning_reason_code: 'semantic_singleton_noise',
                  source_presence_key: 'n/a',
                  preparation_flag_reasons: [],
                  issue_reason: 'semantic_singleton_noise',
                }))}
              />
              <AuditQueryTable
                title="Gated Semantic Noise Samples"
                rows={(compareData?.gated_semantic?.sample_noise_queries || []).map((item) => ({
                  normalized_query_text: item.normalized_query_text,
                  display_query: item.display_query,
                  ranking_value_used: item.ranking_value_used,
                  query_type: item.query_type,
                  intent_type: item.intent_type,
                  pruning_status: 'keep',
                  pruning_reason_code: 'semantic_singleton_noise',
                  source_presence_key: 'n/a',
                  preparation_flag_reasons: [],
                  issue_reason: 'semantic_singleton_noise',
                }))}
              />
              <CompareAssignmentTable
                title="Raw Semantic Top Query Side-By-Side"
                rows={compareData?.raw_comparison?.top_query_assignments || []}
              />
              <CompareAssignmentTable
                title="Gated Semantic Top Query Side-By-Side"
                rows={compareData?.gated_comparison?.top_query_assignments || []}
              />
            </div>
          )}
        </>
      )}
    </div>
  )
}
