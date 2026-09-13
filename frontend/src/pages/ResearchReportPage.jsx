import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, CloudOff, FileText, TrendingUp, Target, ShieldAlert, Building2, BookOpen } from 'lucide-react'
import { researchApi } from '../services/api'
import { typeLabel, formatDate } from '../lib/format'
import StatusBadge from '../components/StatusBadge'
import SourceCard from '../components/SourceCard'
import InsightCard from '../components/InsightCard'
import TrendCard from '../components/TrendCard'
import OpportunityCard from '../components/OpportunityCard'
import RiskCard from '../components/RiskCard'
import CompetitorCard from '../components/CompetitorCard'
import EmptyState from '../components/EmptyState'
import FollowUpBox from '../components/FollowUpBox'

/*
 * Phase 3 overview: the backend grounds research with live web search (Google
 * Search via Gemini, currently rate-limited / quota-exhausted) plus uploaded
 * documents. When no grounded sources are available the synthesis falls back to
 * an explicit "insufficient evidence" shape. This page renders exactly what the
 * backend returns - it never invents sources, figures or scores.
 */

function ProseBlock({ label, children }) {
  if (!children) return null
  return (
    <section className="mt-9">
      <h2 className="text-[0.8rem] font-medium uppercase tracking-wider text-ink-soft">{label}</h2>
      <div className="mt-3 rounded-xl border border-hairline bg-panel p-5 shadow-sm">
        <p className="font-serif text-[1.05rem] leading-relaxed text-ink">{children}</p>
      </div>
    </section>
  )
}

function SectionTitle({ icon: Icon, children, hint }) {
  return (
    <div className="flex items-center justify-between">
      <h2 className="flex items-center gap-2 text-[0.8rem] font-medium uppercase tracking-wider text-ink-soft">
        {Icon && <Icon size={15} strokeWidth={1.75} className="text-evidence" />}
        {children}
      </h2>
      {hint && <span className="text-[0.75rem] text-ink-soft">{hint}</span>}
    </div>
  )
}

export default function ResearchReportPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [report, setReport] = useState(null)
  const [loadedId, setLoadedId] = useState(null)
  const [status, setStatus] = useState('loading') // loading | ready | notfound
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    researchApi
      .get(id)
      .then((data) => {
        if (cancelled) return
        setReport(data)
        setLoadedId(id)
        setStatus('ready')
      })
      .catch(() => {
        if (cancelled) return
        setLoadedId(id)
        setStatus('notfound')
        setError('This report could not be loaded. It may no longer exist, or the backend is unavailable.')
      })
    return () => {
      cancelled = true
    }
  }, [id])

  // Report for the current id is only authoritative once the fetch resolved;
  // until then (including switching between two report URLs) show the skeleton.
  const isReady = status === 'ready' && loadedId === id

  return (
    <div className="mx-auto max-w-4xl px-6 py-10 lg:px-10">
      <button
        onClick={() => navigate(-1)}
        className="flex items-center gap-2 text-[0.85rem] text-ink-soft transition-colors hover:text-ink"
      >
        <ArrowLeft size={15} /> Back
      </button>

      {!isReady && status === 'loading' && (
        <div className="mt-8 space-y-4">
          <div className="h-8 w-2/3 animate-pulse rounded bg-hairline" />
          <div className="h-4 w-40 animate-pulse rounded bg-hairline" />
          <div className="h-28 animate-pulse rounded-xl bg-panel" />
          <div className="h-4 w-11/12 animate-pulse rounded bg-hairline" />
          <div className="h-4 w-4/5 animate-pulse rounded bg-hairline" />
          <p className="pt-2 text-[0.85rem] text-ink-soft">Fetching report…</p>
        </div>
      )}

      {isReady && status === 'notfound' && (
        <>
          <div className="mt-8">
            <EmptyState
              title="Report not available"
              description={error}
              icon={FileText}
            />
          </div>
          <button
            onClick={() => navigate('/reports')}
            className="mt-6 flex items-center gap-2 rounded-lg border border-hairline bg-panel px-4 py-2.5 text-[0.85rem] font-medium text-ink transition-colors hover:border-evidence hover:text-evidence"
          >
            <ArrowLeft size={15} /> Back to reports
          </button>
        </>
      )}

      {isReady && status === 'ready' && report && (
        <ReportContent report={report} />
      )}
    </div>
  )
}

function ReportContent({ report }) {
  const { result, sources = [] } = report
  const hasNoGroundedEvidence = sources.length === 0
  const showSections = result && result.executive_summary

  return (
    <>
      <header className="mt-4">
        <div className="flex flex-wrap items-center gap-3">
          <StatusBadge status={report.status} />
          <span className="rounded-full border border-hairline bg-panel px-2.5 py-1 text-[0.75rem] text-ink-soft">
            {typeLabel(report.research_type)}
          </span>
          <span className="text-[0.78rem] text-ink-soft">Generated {formatDate(report.created_at)}</span>
        </div>
        <h1 className="mt-4 font-serif text-2xl leading-snug text-ink lg:text-[1.7rem]">{report.query}</h1>
      </header>

      {hasNoGroundedEvidence && (
        <div className="mt-6 flex items-start gap-3 rounded-xl border border-signal-soft bg-signal-soft px-4 py-3.5">
          <CloudOff size={18} strokeWidth={1.75} className="mt-0.5 shrink-0 text-signal" />
          <div>
            <p className="text-[0.875rem] font-medium text-ink">Limited source evidence</p>
            <p className="mt-0.5 text-[0.83rem] leading-relaxed text-ink-soft">
              Live web evidence was unavailable for this research. Results are based on available
              indexed/uploaded sources, and may state where evidence is insufficient.
            </p>
          </div>
        </div>
      )}

      {report.status === 'failed' && (
        <div className="mt-6 rounded-xl border border-negative-soft bg-negative-soft px-4 py-3.5 text-[0.875rem] text-negative">
          <p className="font-medium">This research failed to complete.</p>
          {report.error_message && <p className="mt-1 text-[0.83rem]">{report.error_message}</p>}
        </div>
      )}

      {showSections ? (
        <>
          <ProseBlock label="Executive summary">{result.executive_summary}</ProseBlock>

          <section className="mt-9">
            <SectionTitle icon={BookOpen}>Key insights</SectionTitle>
            <div className="mt-3 grid gap-3">
              {result.key_findings.length === 0 ? (
                <EmptyState
                  title="No insights synthesized"
                  description="No grounded evidence was available to build key insights."
                />
              ) : (
                result.key_findings.map((f, i) => <InsightCard key={i} finding={f.finding} evidence={f.evidence} />)
              )}
            </div>
          </section>

          {result.market_overview && (
            <ProseBlock label="Market overview">{result.market_overview}</ProseBlock>
          )}

          <section className="mt-9">
            <SectionTitle icon={TrendingUp}>Trends</SectionTitle>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              {result.trends.length === 0 ? (
                <EmptyState
                  title="Trend data unavailable"
                  description="The engine found insufficient evidence to report market trends."
                />
              ) : (
                result.trends.map((t, i) => <TrendCard key={i} trend={t} />)
              )}
            </div>
          </section>

          <section className="mt-9">
            <SectionTitle icon={Target}>Opportunities</SectionTitle>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              {result.opportunities.length === 0 ? (
                <EmptyState
                  title="Opportunity data unavailable"
                  description="No grounded opportunities could be identified from the available evidence."
                />
              ) : (
                result.opportunities.map((o, i) => <OpportunityCard key={i} opportunity={o} />)
              )}
            </div>
          </section>

          <section className="mt-9">
            <SectionTitle icon={ShieldAlert}>Risks</SectionTitle>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              {result.risks.length === 0 ? (
                <EmptyState
                  title="Risk data unavailable"
                  description="No grounded risks could be identified from the available evidence."
                />
              ) : (
                result.risks.map((r, i) => <RiskCard key={i} risk={r} />)
              )}
            </div>
          </section>

          <section className="mt-9">
            <SectionTitle icon={Building2}>Competitor analysis</SectionTitle>
            <div className="mt-3 grid gap-3">
              {result.competitors.length === 0 ? (
                <EmptyState
                  title="Competitor data unavailable"
                  description="The engine found insufficient evidence to profile competitors."
                />
              ) : (
                result.competitors.map((c, i) => <CompetitorCard key={i} competitor={c} />)
              )}
            </div>
          </section>

          {result.conclusion && <ProseBlock label="Conclusion">{result.conclusion}</ProseBlock>}
        </>
      ) : (
        <div className="mt-8">
          <EmptyState
            title="No report content"
            description="This research completed without producing a synthesis result."
          />
        </div>
      )}

      <section className="mt-10">
        <SectionTitle hint={`${sources.length} ${sources.length === 1 ? 'source' : 'sources'}`} icon={FileText}>
          Sources
        </SectionTitle>
        <div className="mt-3 space-y-3">
          {sources.length === 0 ? (
            <EmptyState
              title="No grounding sources recorded"
              description="This report was synthesized without recorded sources. Upload documents and retry to get grounded citations."
              icon={FileText}
            />
          ) : (
            sources.map((s) => <SourceCard key={s.id} source={s} />)
          )}
        </div>
      </section>

      <section className="mt-10">
        <FollowUpBox query={report.query} />
      </section>
    </>
  )
}