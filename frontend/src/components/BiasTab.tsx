import React, { useState, useMemo } from 'react';
import { Search, X } from 'lucide-react';

interface PairBias {
  name: string;
  asset_class: string;
  base_asset: string;
  quote_asset: string;
  base_score: number;
  quote_score: number;
  net_differential?: number;
  combined_bias: number;
  direction: string;
  momentum_base?: number;
  momentum_quote?: number;
}

interface BreakdownItem {
  indicator: string;
  value: number | null;
  unit: string;
  date: string | null;
  score: number;
  tier: string;
  weight: number;
  direction: string;
  contribution: number;
}

// Per-event analytical record emitted by build_fundamental_bias.py
interface EventItem {
  date: string;
  time: string;
  event: string;
  impact: string;
  actual_raw: string;
  forecast_raw: string;
  previous_raw: string;
  actual_num: number | null;
  forecast_num: number | null;
  previous_num: number | null;
  deviation: number | null;
  d_score: number | null;
  weight: number;
  direction: string;
}

interface Props {
  data: any;
}

export default function BiasTab({ data }: Props) {
  const [search, setSearch] = useState('');
  const [selectedPair, setSelectedPair] = useState<PairBias | null>(null);
  const [sortField, setSortField] = useState<'combined_bias' | 'name'>('combined_bias');
  const [sortAsc, setSortAsc] = useState(false);

  const allPairs: PairBias[] = data?.pairs || [];
  const baseScores: Record<string, number> = data?.base_scores || {};
  const eventBreakdowns: Record<string, EventItem[]> = data?.event_breakdowns || {};
  const scoreBreakdowns: Record<string, BreakdownItem[]> = data?.score_breakdowns || {};
  const analysisWindowDays = data?.analysis_window_days || 14;

  const pairsByClass = useMemo(() => {
    const groups: Record<string, PairBias[]> = {};
    for (const p of allPairs) {
      const cls = p.asset_class || 'OTHER';
      if (!groups[cls]) groups[cls] = [];
      groups[cls].push(p);
    }
    return groups;
  }, [allPairs]);

  const classOrder = ['FX', 'METAL', 'ENERGY', 'INDEX', 'CRYPTO', 'OTHER'];
  const classLabels: Record<string, string> = {
    FX: 'Currency Pairs',
    METAL: 'Precious Metals',
    ENERGY: 'Energy',
    INDEX: 'Equity Indices',
    CRYPTO: 'Cryptocurrencies',
    OTHER: 'Other',
  };

  const filteredAndSorted = (pairs: PairBias[]) => {
    let filtered = pairs;
    if (search.trim()) {
      const q = search.toLowerCase();
      filtered = pairs.filter(p => p.name.toLowerCase().includes(q));
    }
    return [...filtered].sort((a, b) => {
      if (sortField === 'name') {
        return sortAsc ? a.name.localeCompare(b.name) : b.name.localeCompare(a.name);
      }
      return sortAsc
        ? a.combined_bias - b.combined_bias
        : b.combined_bias - a.combined_bias;
    });
  };

  const getScoreColor = (score: number) => {
    if (score >= 8) return 'text-emerald-400';
    if (score >= 6) return 'text-emerald-300';
    if (score >= 4.1) return 'text-gray-400';
    if (score >= 2.1) return 'text-red-300';
    return 'text-red-400';
  };

  const getBadge = (direction: string) => {
    if (direction.includes('Bullish'))
      return 'bg-emerald-900/40 text-emerald-400 border-emerald-700/40';
    if (direction.includes('Bearish'))
      return 'bg-red-900/40 text-red-400 border-red-700/40';
    return 'bg-gray-700/40 text-gray-400 border-gray-600/40';
  };
  // ── Compact number formatting (K / M / B) ─────────────────────────────────────
  const fmtNum = (n: number | null | undefined): string => {
    if (n === null || n === undefined || Number.isNaN(n)) return '—';
    const abs = Math.abs(n);
    const sign = n < 0 ? '-' : '';
    if (abs >= 1e9) return `${sign}${(abs / 1e9).toFixed(2)}B`;
    if (abs >= 1e6) return `${sign}${(abs / 1e6).toFixed(2)}M`;
    if (abs >= 1e3) return `${sign}${(abs / 1e3).toFixed(1)}K`;
    if (Number.isInteger(n)) return n.toString();
    return (Math.round(n * 100) / 100).toString();
  };

  // Prefer the clean raw string; otherwise compact numeric.
  const displayVal = (raw: string, num: number | null) =>
    raw && raw.trim() && raw.trim() !== '—' ? raw : fmtNum(num);

  const getImpactBadge = (impact: string) => {
    if (impact === 'High') return 'bg-red-900/40 text-red-400 border-red-700/40';
    if (impact === 'Medium') return 'bg-orange-900/40 text-orange-400 border-orange-700/40';
    if (impact === 'Low') return 'bg-yellow-900/40 text-yellow-400 border-yellow-700/40';
    return 'bg-gray-700/40 text-gray-400 border-gray-600/40';
  };

  // ── Fundamental Verdict Paragraph ─────────────────────────────────────────────
  const buildVerdict = (p: PairBias): string => {
    const diff = p.net_differential !== undefined ? p.net_differential : p.base_score - p.quote_score;
    const baseEvents = (eventBreakdowns[p.base_asset] || []).filter(e => e.d_score !== null);
    const quoteEvents = (eventBreakdowns[p.quote_asset] || []).filter(e => e.d_score !== null);
    const topBase = [...baseEvents]
      .sort((a, b) => Math.abs(b.d_score ?? 0) - Math.abs(a.d_score ?? 0))
      .slice(0, 2);
    const topQuote = [...quoteEvents]
      .sort((a, b) => Math.abs(b.d_score ?? 0) - Math.abs(a.d_score ?? 0))
      .slice(0, 2);

    const absDiff = Math.abs(diff);
    let strength;
    if (absDiff >= 2.0) strength = 'overwhelmingly';
    else if (absDiff >= 1.0) strength = 'significantly';
    else if (absDiff >= 0.5) strength = 'moderately';
    else strength = 'only marginally';

    const label = p.direction.includes('Bullish') ? 'Bullish' : p.direction.includes('Bearish') ? 'Bearish' : 'Neutral';

    const baseBit = topBase.length > 0
      ? `Recent ${p.base_asset} data (${topBase.map(e => `"${e.event}" (${e.direction})`).join(', ')}) reinforces this view.`
      : `No recent ${p.base_asset} calendar events were available in the ${analysisWindowDays}-day window.`;
    const quoteBit = topQuote.length > 0
      ? `Meanwhile ${p.quote_asset} data (${topQuote.map(e => `"${e.event}" (${e.direction})`).join(', ')}) moves in the opposite direction.`
      : `No recent ${p.quote_asset} calendar events were available in the ${analysisWindowDays}-day window.`;

    if (label === 'Neutral') {
      return `The ${p.name} pair sits near equilibrium: ${p.base_asset} scores ${p.base_score.toFixed(1)} against ${p.quote_asset}'s ${p.quote_score.toFixed(1)}, for a net differential of ${diff >= 0 ? '+' : ''}${diff.toFixed(1)}. Neither side carries a clear macroeconomic edge. ${baseBit} ${quoteBit}`;
    }
    return `The ${p.name} pair is ${label.toLowerCase()} overall. ${p.base_asset} carries a fundamental strength score of ${p.base_score.toFixed(1)} versus ${p.quote_asset}'s ${p.quote_score.toFixed(1)} — a net differential of ${diff >= 0 ? '+' : ''}${diff.toFixed(1)} that ${diff > 0 ? 'favors' : 'weighs against'} the base currency ${strength}. ${baseBit} ${quoteBit}`;
  };

  // ── Currency breakdown table (Base & Quote legs) ──────────────────────────────
  const renderCurrencyTable = (currency: string) => {
    const events = (eventBreakdowns[currency] || [])
      .filter(e => e.d_score !== null && e.d_score !== undefined)
      .slice()
      .sort((a, b) => (b.date || '').localeCompare(a.date || ''))
      .slice(0, 8);

    if (events.length === 0) {
      return (
        <div className="text-center py-6 text-2xs text-gray-500">
          No released economic events for {currency} in the {analysisWindowDays}-day window.
        </div>
      );
    }

    return (
      <div className="overflow-x-auto">
        <table className="w-full text-[11px]">
          <thead>
            <tr className="border-b border-dark-border text-2xs text-gray-500">
              <th className="text-left py-2 pl-3 pr-2 font-medium">Date</th>
              <th className="text-left py-2 px-2 font-medium">Event</th>
              <th className="text-center py-2 px-2 font-medium">Impact</th>
              <th className="text-right py-2 px-2 font-medium">Actual</th>
              <th className="text-right py-2 px-2 font-medium">Forecast</th>
              <th className="text-center py-2 pr-3 font-medium">Score</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-dark-border">
            {events.map((e, i) => (
              <tr key={i} className="hover:bg-dark-card/50">
                <td className="py-1.5 pl-3 pr-2 whitespace-nowrap text-gray-400 font-mono">
                  {e.date ? (e.date.length > 10 ? e.date.slice(0, 10) : e.date) : '—'}
                </td>
                <td className="py-1.5 px-2 text-gray-300 max-w-[220px] truncate" title={e.event}>
                  {e.event}
                </td>
                <td className="py-1.5 px-2 text-center">
                  <span className={`inline-flex items-center gap-1 text-2xs px-1.5 py-0.5 rounded border ${getImpactBadge(e.impact)}`}>
                    <span className={`w-1.5 h-1.5 rounded-full ${e.impact === 'High' ? 'bg-red-500' : e.impact === 'Medium' ? 'bg-orange-500' : e.impact === 'Low' ? 'bg-yellow-500' : 'bg-gray-500'}`} />
                    {e.impact}
                  </span>
                </td>
                <td className="py-1.5 px-2 text-right font-mono text-gray-200 whitespace-nowrap">
                  {displayVal(e.actual_raw, e.actual_num)}
                </td>
                <td className="py-1.5 px-2 text-right font-mono text-gray-400 whitespace-nowrap">
                  {displayVal(e.forecast_raw, e.forecast_num)}
                </td>
                <td className={`py-1.5 pr-3 text-center font-mono font-bold ${getScoreColor(5 + (e.d_score ?? 0) * 4)}`}>
                  {((e.d_score ?? 0) >= 0 ? '+' : '')}{(e.d_score ?? 0).toFixed(2)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  };

  // Detail Modal — Relative Strength + per-currency event breakdown + verdict
  const renderModal = () => {
    if (!selectedPair) return null;
    const p = selectedPair;

    const baseBreakdown = scoreBreakdowns[p.base_asset] || [];
    const quoteBreakdown = scoreBreakdowns[p.quote_asset] || [];

    const netDiff = p.net_differential !== undefined
      ? p.net_differential
      : Math.round((p.base_score - p.quote_score) * 100) / 100;
    const diffColor = netDiff >= 0.5 ? 'text-emerald-400' : netDiff <= -0.5 ? 'text-red-400' : 'text-gray-400';
    const diffLabel = p.direction.includes('Bullish') ? 'Bullish' : p.direction.includes('Bearish') ? 'Bearish' : 'Neutral';
    const diffLabelBg = p.direction.includes('Bullish')
      ? 'bg-emerald-900/40 text-emerald-400 border-emerald-700/40'
      : p.direction.includes('Bearish')
        ? 'bg-red-900/40 text-red-400 border-red-700/40'
        : 'bg-gray-700/40 text-gray-400 border-gray-600/40';

    const baseHasEvents = (eventBreakdowns[p.base_asset] || []).some(e => e.d_score !== null && e.d_score !== undefined);
    const quoteHasEvents = (eventBreakdowns[p.quote_asset] || []).some(e => e.d_score !== null && e.d_score !== undefined);

    return (
      <div className="modal-overlay" onClick={() => setSelectedPair(null)}>
        <div className="modal-content max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
          <div className="flex items-center justify-between p-4 border-b border-dark-border">
            <h3 className="text-sm font-bold text-white">{p.name}</h3>
            <button onClick={() => setSelectedPair(null)} className="text-gray-400 hover:text-white">
              <X size={18} />
            </button>
          </div>

          <div className="divide-y divide-dark-border">
            {/* ═══ Relative Strength Header ═══ */}
            <div className="p-4">
              <div className="text-2xs text-gray-500 uppercase tracking-wider mb-3 font-semibold">
                Relative Strength Differential
              </div>
              <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-lg font-bold text-white">{p.base_asset}</span>
                  <span className={`font-mono text-lg font-bold ${getScoreColor(p.base_score)}`}>
                    ({p.base_score.toFixed(1)})
                  </span>
                </div>
                <span className="text-gray-600 text-xs">vs</span>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-lg font-bold text-white">{p.quote_asset}</span>
                  <span className={`font-mono text-lg font-bold ${getScoreColor(p.quote_score)}`}>
                    ({p.quote_score.toFixed(1)})
                  </span>
                </div>
                <div className="ml-auto text-right">
                  <div className="text-2xs text-gray-500 uppercase">Net Differential</div>
                  <div className={`font-mono text-lg font-bold ${diffColor}`}>
                    {netDiff >= 0 ? '+' : ''}{netDiff.toFixed(1)}
                    <span className={`ml-2 text-xs px-2 py-0.5 rounded border align-middle ${diffLabelBg}`}>
                      {diffLabel}
                    </span>
                  </div>
                </div>
              </div>
              <div className="mt-3 relative h-1.5 rounded-full bg-dark-border overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${netDiff >= 0 ? 'bg-emerald-500' : 'bg-red-500'}`}
                  style={{
                    width: `${Math.min(50, Math.abs(netDiff) * 5)}%`,
                    marginLeft: '50%',
                    transform: netDiff >= 0 ? 'none' : 'translateX(-100%)',
                  }}
                />
              </div>
              <div className="mt-1 flex justify-between text-[10px] text-gray-600 font-mono">
                <span>Bearish {p.base_asset}</span>
                <span>Neutral</span>
                <span>Bullish {p.base_asset}</span>
              </div>
            </div>

{/* ═══ Base Currency Data Breakdown ═══ */}
            <div className="p-4">
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-xs font-semibold text-white">
                  {p.base_asset} — Recent Economic Data
                </h4>
                <span className={`text-2xs px-2 py-0.5 rounded border bg-gray-800 ${getScoreColor(p.base_score)}`}>
                  Strength {p.base_score.toFixed(1)}/10
                </span>
              </div>
              {baseHasEvents ? renderCurrencyTable(p.base_asset) : (
                <div className="text-center py-4 text-2xs text-gray-500">
                  {p.asset_class === 'FX'
                    ? `No released economic events for ${p.base_asset} in the ${analysisWindowDays}-day window.`
                    : `${p.base_asset} is a USD-priced ${p.asset_class.toLowerCase()} asset — its score is driven by the inverse USD relationship (11 − S_USD).`}
                </div>
              )}
            </div>

            {/* ═══ Quote Currency Data Breakdown ═══ */}
            <div className="p-4">
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-xs font-semibold text-white">
                  {p.quote_asset} — Recent Economic Data
                </h4>
                <span className={`text-2xs px-2 py-0.5 rounded border bg-gray-800 ${getScoreColor(p.quote_score)}`}>
                  Strength {p.quote_score.toFixed(1)}/10
                </span>
              </div>
              {quoteHasEvents ? renderCurrencyTable(p.quote_asset) : (
                <div className="text-center py-4 text-2xs text-gray-500">
                  {`No released economic events for ${p.quote_asset} in the ${analysisWindowDays}-day window.`}
                </div>
              )}
            </div>

            {/* ═══ Fundamental Verdict Summary ═══ */}
            <div className="p-4">
              <div className="text-2xs text-gray-500 uppercase tracking-wider mb-2 font-semibold">
                Fundamental Verdict
              </div>
              <div className="card p-3">
                <p className="text-xs text-gray-300 leading-relaxed">
                  {buildVerdict(p)}
                </p>
                <div className="mt-3 flex items-center justify-between text-2xs text-gray-500">
                  <span>Base {p.base_score.toFixed(1)} · Quote {p.quote_score.toFixed(1)}</span>
                  <span>Analysis window: {analysisWindowDays} days</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  };
return (
    <div>
      {/* Header with search */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-4">
        <div>
          <h2 className="text-sm font-semibold text-white">Master Bias Matrix</h2>
          <p className="text-2xs text-gray-500 mt-0.5">
            {allPairs.length} pairs · Sorted by strength
          </p>
        </div>
        <div className="relative w-full sm:w-64">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
          <input
            type="text"
            placeholder="Search pairs..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="filter-input pl-8 w-full"
          />
        </div>
      </div>

      {/* Pairs by class */}
      {classOrder.map(cls => {
        const pairs = pairsByClass[cls];
        if (!pairs || pairs.length === 0) return null;
        const sorted = filteredAndSorted(pairs);
        if (sorted.length === 0) return null;

        return (
          <div key={cls} className="mb-6">
            <h3 className="text-2xs text-gray-500 uppercase tracking-wider mb-2 font-semibold">
              {classLabels[cls] || cls}
              <span className="ml-2 text-gray-600">({pairs.length})</span>
            </h3>

            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-dark-border">
                    <th
                      className="text-left py-2 px-3 text-gray-500 font-medium cursor-pointer hover:text-gray-300"
                      onClick={() => { setSortField('name'); setSortAsc(!sortAsc); }}
                    >
                      Name {sortField === 'name' && (sortAsc ? '↑' : '↓')}
                    </th>
                    <th className="text-center py-2 px-3 text-gray-500 font-medium">Base</th>
                    <th className="text-center py-2 px-3 text-gray-500 font-medium">Quote</th>
                    <th
                      className="text-center py-2 px-3 text-gray-500 font-medium cursor-pointer hover:text-gray-300"
                      onClick={() => { setSortField('combined_bias'); setSortAsc(!sortAsc); }}
                    >
                      Bias {sortField === 'combined_bias' && (sortAsc ? '↑' : '↓')}
                    </th>
                    <th className="text-center py-2 px-3 text-gray-500 font-medium">Direction</th>
                    <th className="text-center py-2 px-3 text-gray-500 font-medium">Detail</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-dark-border">
                  {sorted.map((p, i) => (
                    <tr key={i} className="hover:bg-dark-card/50 transition-colors">
                      <td className="py-2 px-3 font-medium text-white">{p.name}</td>
                      <td className={`py-2 px-3 text-center font-mono ${getScoreColor(p.base_score)}`}>
                        {p.base_score.toFixed(1)}
                      </td>
                      <td className={`py-2 px-3 text-center font-mono ${getScoreColor(p.quote_score)}`}>
                        {p.quote_score.toFixed(1)}
                      </td>
                      <td className={`py-2 px-3 text-center font-mono font-bold text-sm ${getScoreColor(p.combined_bias)}`}>
                        {p.combined_bias.toFixed(1)}
                      </td>
                      <td className="py-2 px-3 text-center">
                        <span className={`text-2xs px-2 py-0.5 rounded border ${getBadge(p.direction)}`}>
                          {p.direction}
                        </span>
                      </td>
                      <td className="py-2 px-3 text-center">
                        <button
                          onClick={() => setSelectedPair(p)}
                          className="text-2xs px-2 py-1 bg-dark-border rounded text-gray-400 hover:text-white hover:bg-gray-600 transition-colors"
                        >
                          Analyze
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        );
      })}

      {allPairs.length === 0 && (
        <div className="text-center py-12 text-gray-500">
          No pair data available.
        </div>
      )}

      {renderModal()}
    </div>
  );
}
