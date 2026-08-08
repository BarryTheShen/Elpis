import type { CandidateItem } from '../lib/types';
import { formatDateOnly } from '../lib/dates';

interface CandidateCardProps {
  candidate: CandidateItem;
}

function countEvidence(value: number | string[] | undefined): number {
  if (Array.isArray(value)) return value.length;
  return typeof value === 'number' ? value : 0;
}

function scoreLabel(value: number): string {
  if (!Number.isFinite(value)) return '—';
  return value.toFixed(2);
}

/**
 * A compact, read-first card for ranked candidates. Candidate cards link only
 * to the source URL; unpublished candidates must never open ItemDetailPanel.
 */
export function CandidateCard({ candidate }: CandidateCardProps) {
  const evidence = candidate.evidence;
  const selected = Boolean(evidence?.selected);
  const matchedTerms = Array.isArray(evidence?.matched_terms)
    ? evidence.matched_terms.filter(Boolean)
    : [];
  const titleMatches = countEvidence(evidence?.title_matches);
  const contextMatches = countEvidence(evidence?.context_matches);
  const numericSignals = Object.entries(candidate.score_breakdown ?? {})
    .filter(([name, value]) => name !== 'llm_reason' && typeof value === 'number' && Number.isFinite(value))
    .sort(([, first], [, second]) => Math.abs(second ?? 0) - Math.abs(first ?? 0))
    .slice(0, 3);

  return (
    <article className="flex h-full flex-col rounded-lg border border-[#e6e5e3] bg-white p-5 transition-colors hover:border-[#c7dff2] dark:border-[#3b3a37] dark:bg-[#20201e] dark:hover:border-[#52799c]">
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs font-semibold uppercase tracking-[0.08em] text-[#7d7a75] dark:text-[#b4b1ab]">
        <span>Rank #{candidate.rank}</span>
        <span className="rounded-full bg-[#e5f2fc] px-2 py-1 normal-case tracking-normal text-[#1d5f9f] dark:bg-[#1c3852] dark:text-[#a6d2f8]">
          Score {scoreLabel(candidate.preference_score)}
        </span>
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5" aria-label="Candidate evidence">
        <span className="rounded-full border border-[#d8e8f5] px-2 py-1 text-xs text-[#1d5f9f] dark:border-[#36536d] dark:text-[#a6d2f8]">
          {selected ? 'Briefed' : 'Ranked candidate'}
        </span>
        {titleMatches > 0 && (
          <span className="rounded-full border border-[#e6e5e3] px-2 py-1 text-xs text-[#5e5b56] dark:border-[#3b3a37] dark:text-[#cbc8c1]">
            Title {titleMatches}
          </span>
        )}
        {contextMatches > 0 && (
          <span className="rounded-full border border-[#e6e5e3] px-2 py-1 text-xs text-[#5e5b56] dark:border-[#3b3a37] dark:text-[#cbc8c1]">
            Context {contextMatches}
          </span>
        )}
        {matchedTerms.slice(0, 4).map((term) => (
          <span
            key={term}
            className="rounded-full bg-[#f0efed] px-2 py-1 text-xs text-[#5e5b56] dark:bg-[#2a2927] dark:text-[#cbc8c1]"
          >
            {term}
          </span>
        ))}
        {numericSignals.map(([name, value]) => (
          <span
            key={name}
            className="rounded-full border border-[#e6e5e3] px-2 py-1 text-xs text-[#5e5b56] dark:border-[#3b3a37] dark:text-[#cbc8c1]"
          >
            {name.replace(/_/g, ' ')} {value != null && value >= 0 ? '+' : ''}
            {typeof value === 'number' ? value.toFixed(2) : '0.00'}
          </span>
        ))}
      </div>

      <h2 className="mt-4 text-lg font-semibold leading-snug tracking-[-0.015em] text-[#2c2c2b] dark:text-[#f4f3f1]">
        <a
          href={candidate.url}
          target="_blank"
          rel="noreferrer"
          className="underline decoration-transparent underline-offset-4 transition-colors hover:decoration-current focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2783de]"
        >
          {candidate.title}
        </a>
      </h2>

      <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-[#7d7a75] dark:text-[#b4b1ab]">
        <span className="font-medium text-[#5e5b56] dark:text-[#cbc8c1]">{candidate.source}</span>
        <span aria-hidden="true">·</span>
        <span>{candidate.category}</span>
        {candidate.published_at && (
          <>
            <span aria-hidden="true">·</span>
            <time dateTime={candidate.published_at}>
              {formatDateOnly(candidate.published_at, { year: true })}
            </time>
          </>
        )}
      </div>

      {candidate.excerpt && (
        <p className="mt-3 line-clamp-4 text-sm leading-6 text-[#5e5b56] dark:text-[#cbc8c1]">
          {candidate.excerpt}
        </p>
      )}

      {evidence?.relevance_reason && (
        <p className="mt-3 border-l-2 border-[#d8e8f5] pl-3 text-xs leading-5 text-[#7d7a75] dark:border-[#36536d] dark:text-[#b4b1ab]">
          {evidence.relevance_reason}
        </p>
      )}

      <div className="mt-auto pt-5">
        <a
          href={candidate.url}
          target="_blank"
          rel="noreferrer"
          className="inline-flex min-h-9 items-center rounded-md text-sm font-semibold text-[#1d5f9f] underline underline-offset-4 hover:text-[#164a7c] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2783de] dark:text-[#a6d2f8] dark:hover:text-white"
        >
          Read at {candidate.source}
          <span aria-hidden="true" className="ml-1">↗</span>
        </a>
      </div>
    </article>
  );
}
