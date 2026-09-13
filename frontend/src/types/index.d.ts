/*
 * Type definitions mirroring the backend MarketIQ Pydantic response models.
 * Backend source of truth: backend/app/schemas/research.py, schemas/dashboard.py,
 * schemas/document.py. Do not invent fields that the backend does not return.
 */

export interface QuickStats {
  researches_completed: number
  sources_analyzed: number
  companies_analyzed: number
  trends_detected: number
}

export interface HealthResponse {
  status: string
  environment: string
  database: string
  gemini_configured: boolean
}

export type ResearchStatus = 'pending' | 'running' | 'completed' | 'failed'

export interface ResearchCard {
  id: string
  query: string
  research_type: string
  status: ResearchStatus
  updated_at: string
}

export interface KeyFinding {
  finding: string
  evidence: string[]
}

export interface Trend {
  trend: string
  impact: 'high' | 'medium' | 'low'
  description: string
}

export interface Risk {
  risk: string
  severity: 'high' | 'medium' | 'low'
  mitigation: string | null
}

export interface Opportunity {
  opportunity: string
  potential_impact: string
}

export interface Competitor {
  company: string
  market_share: string | null
  strengths: string[]
  weaknesses: string[]
  evidence?: string[]
}

export interface ResearchSynthesis {
  executive_summary: string
  key_findings: KeyFinding[]
  market_overview: string
  trends: Trend[]
  opportunities: Opportunity[]
  risks: Risk[]
  competitors: Competitor[]
  conclusion: string
  source_ids: string[]
}

export interface Source {
  id: string
  research_id: string
  title: string
  url: string | null
  source_name: string
  source_type: 'web' | 'document' | 'news'
  relevance: number | null
  is_mock: boolean
  published_at: string | null
}

export interface ResearchResponse {
  research_id: string
  query: string
  research_type: string
  status: ResearchStatus
  created_at: string
  updated_at: string
  error_message: string | null
  result: ResearchSynthesis | null
  sources: Source[]
}

export interface ResearchRequest {
  query: string
  research_type?: string
  document_ids?: string[]
}

export interface DocumentResponse {
  id: string
  filename: string
  file_type: string
  file_size: number
  status: string
  chunk_count: number
  error_message: string | null
  uploaded_at: string
}