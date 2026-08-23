import React from 'react';

interface CftcPosition {
  report_date: string;
  noncomm_long: number;
  noncomm_short: number;
  long_ratio?: number;
  cftc_score?: number;
  sentiment?: string;
  net_speculative: number;
  weekly_change: number;
  weekly_change_pct?: number;
  percentile_52w: number;
  asset_mgr_long?: number;
  asset_mgr_short?: number;
  lev_funds_long?: number;
  lev_funds_short?: number;
}

// New task-schema entry (asset symbol keyed)
interface CftcAssetData {
  asset: string;
  category: string;
  long_contracts: number;
  short_contracts: number;
  long_percentage: number;
  short_percentage: number;
  weekly_change_pct?: number | null;
  sentiment: string;
  cftc_score: number;
}

interface Props {
  data: any;
}

// Tiered bias labels centered at 50.0% long ratio
function getLongRatioSignal(longRatio: number) {
  const lr = longRatio;
  if (lr > 50.0) {
    if (lr >= 75.0) return { label: 'Strongly Bullish', color: 'text-emerald-400', bg: 'bg-emerald-900/40' };
    if (lr >= 60.0) return { label: 'Moderately Bullish', color: 'text-emerald-400', bg: 'bg-emerald-900/30' };
    return { label: 'Mildly Bullish', color: 'text-emerald-300', bg: 'bg-emerald-900/20' };
  }
  if (lr < 50.0) {
    if (lr <= 24.9) return { label: 'Strongly Bearish', color: 'text-red-400', bg: 'bg-red-900/40' };
    if (lr <= 40.0) return { label: 'Moderately Bearish', color: 'text-red-400', bg: 'bg-red-900/30' };
    return { label: 'Mildly Bearish', color: 'text-red-300', bg: 'bg-red-900/20' };
  }
  return { label: 'Neutral', color: 'text-gray-400', bg: 'bg-gray-700/30' };
}

function computeLongRatio(pos: CftcPosition): number {
  if (pos.long_ratio !== undefined && pos.long_ratio !== null) return pos.long_ratio;
  const total = (pos.noncomm_long || 0) + (pos.noncomm_short || 0);
  if (total <= 0) return 50.0;
  return (pos.noncomm_long / total) * 100;
}

// Weekly Net Positioning Change (ΔW) — visual momentum badge only.
// Muted neutral/gray so it never detracts from the overall positioning bar.
function WeeklyChangeBadge({ pct }: { pct: number | null | undefined }) {
  if (pct === null || pct === undefined || isNaN(pct)) return null;
  const positive = pct >= 0;
  return (
    <span
      className="inline-flex items-center gap-1 text-2xs px-1.5 py-0.5 rounded font-mono font-medium bg-gray-700/40 text-gray-400"
      title="Weekly Net Positioning Change (momentum only - does not affect bias)"
    >
      {positive ? '▲' : '▼'} {positive ? '+' : ''}{pct.toFixed(2)}% WoW
    </span>
  );
}

// Dual-color Overall Long vs. Short ratio bar (green Long / red Short)
function LongShortBar({ longPct, shortPct }: { longPct: number; shortPct: number }) {
  const l = Math.max(0, Math.min(100, longPct));
  const s = Math.max(0, Math.min(100, shortPct));
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 flex h-2 rounded-full overflow-hidden bg-gray-700">
        <div className="bg-emerald-500" style={{ width: `${l}%` }} />
        <div className="bg-red-500" style={{ width: `${s}%` }} />
      </div>
      <span className="text-2xs font-mono text-gray-300 whitespace-nowrap">
        {l.toFixed(2)}% L / {s.toFixed(2)}% S
      </span>
    </div>
  );
}

export default function CftcTab({ data }: Props) {
  // Prefer the new task-schema `data` (asset symbols), fall back to `positions`.
  const assetData: Record<string, CftcAssetData> = data?.data || {};
  const positions: Record<string, CftcPosition> = data?.positions || {};

  const hasAssetData = Object.keys(assetData).length > 0;
  const entries = hasAssetData
    ? Object.entries(assetData).map(([key, a]) => ({
        key,
        label: a.asset,
        longPct: a.long_percentage,
        shortPct: a.short_percentage,
        weeklyPct: a.weekly_change_pct ?? 0,
        sentiment: a.sentiment,
        score: a.cftc_score,
        netSpec: (a.long_contracts || 0) - (a.short_contracts || 0),
        reportDate: '',
      }))
    : Object.entries(positions).map(([key, pos]) => {
        const lr = computeLongRatio(pos);
        const signal = getLongRatioSignal(lr);
        return {
          key,
          label: key,
          longPct: lr,
          shortPct: 100 - lr,
          weeklyPct: pos.weekly_change_pct ?? 0,
          sentiment: pos.sentiment || signal.label,
          score: pos.cftc_score ?? 5.0,
          netSpec: pos.net_speculative,
          reportDate: pos.report_date,
        };
      });

  if (entries.length === 0) {
    return (
      <div className="text-center py-12 text-gray-500">
        No CFTC data available. The weekly report is released every Friday.
      </div>
    );
  }

  return (
    <div>
      <div className="mb-4">
        <h2 className="text-sm font-semibold text-white">CFTC Commitments of Traders</h2>
        <p className="text-2xs text-gray-500 mt-0.5">
          All-Time Overall Long vs. Short Positioning · {entries.length} markets
        </p>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        {entries.slice(0, 4).map((e) => {
          const signal = getLongRatioSignal(e.longPct);
          return (
            <div key={e.key} className="card p-3">
              <div className="text-2xs text-gray-500 uppercase mb-1">{e.label}</div>
              <div className={`stat-value ${e.netSpec >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                {e.netSpec >= 0 ? '+' : ''}{(e.netSpec / 1000).toFixed(0)}K
              </div>
              {/* Overall Long vs. Short dual-color bar */}
              <div className="mt-1">
                <LongShortBar longPct={e.longPct} shortPct={e.shortPct} />
              </div>
              <div className="flex items-center justify-between mt-1">
                <div className="text-2xs text-gray-500">{e.sentiment}</div>
                {/* ΔW momentum badge — muted, visual only, never flips bias */}
                <WeeklyChangeBadge pct={e.weeklyPct} />
              </div>
            </div>
          );
        })}
      </div>

      {/* Full table */}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-dark-border">
              <th className="text-left py-2 px-3 text-gray-500 font-medium uppercase tracking-wider">Market</th>
              <th className="text-right py-2 px-3 text-gray-500 font-medium uppercase tracking-wider">Long Contracts</th>
              <th className="text-right py-2 px-3 text-gray-500 font-medium uppercase tracking-wider">Short Contracts</th>
              <th className="text-right py-2 px-3 text-gray-500 font-medium uppercase tracking-wider">Net Speculative</th>
              <th className="text-center py-2 px-3 text-gray-500 font-medium uppercase tracking-wider">Overall Long vs Short</th>
              <th className="text-center py-2 px-3 text-gray-500 font-medium uppercase tracking-wider">Weekly ΔW</th>
              <th className="text-center py-2 px-3 text-gray-500 font-medium uppercase tracking-wider">Score</th>
              <th className="text-center py-2 px-3 text-gray-500 font-medium uppercase tracking-wider">Bias</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-dark-border">
            {entries.map((e) => {
              const signal = getLongRatioSignal(e.longPct);
              const longContracts = hasAssetData
                ? (assetData[e.key]?.long_contracts ?? 0)
                : (positions[e.key]?.noncomm_long ?? 0);
              const shortContracts = hasAssetData
                ? (assetData[e.key]?.short_contracts ?? 0)
                : (positions[e.key]?.noncomm_short ?? 0);
              return (
                <tr key={e.key} className="hover:bg-dark-card/50 transition-colors">
                  <td className="py-2 px-3 font-bold text-white">{e.label}</td>
                  <td className="py-2 px-3 text-right text-emerald-400 font-mono">
                    {longContracts.toLocaleString()}
                  </td>
                  <td className="py-2 px-3 text-right text-red-400 font-mono">
                    {shortContracts.toLocaleString()}
                  </td>
                  <td className={`py-2 px-3 text-right font-mono font-bold ${
                    e.netSpec >= 0 ? 'text-emerald-400' : 'text-red-400'
                  }`}>
                    {e.netSpec >= 0 ? '+' : ''}{e.netSpec.toLocaleString()}
                  </td>
                  <td className="py-2 px-3">
                    <LongShortBar longPct={e.longPct} shortPct={e.shortPct} />
                  </td>
                  {/* ΔW — visual momentum only, never flips the bias */}
                  <td className="py-2 px-3 text-center">
                    <WeeklyChangeBadge pct={e.weeklyPct} />
                  </td>
                  <td className="py-2 px-3 text-center">
                    <span className={`font-mono font-bold ${signal.color}`}>{e.score.toFixed(1)}</span>
                  </td>
                  <td className="py-2 px-3 text-center">
                    <span className={`text-2xs px-2 py-0.5 rounded font-medium ${signal.bg} ${signal.color}`}>
                      {e.sentiment}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}