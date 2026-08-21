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
// This NEVER overrides the overall L% bias.
function WeeklyChangeBadge({ pct }: { pct: number }) {
  const positive = pct >= 0;
  return (
    <span
      className={`inline-flex items-center gap-1 text-2xs px-1.5 py-0.5 rounded font-mono font-medium ${
        positive ? 'bg-blue-900/30 text-blue-300' : 'bg-orange-900/30 text-orange-300'
      }`}
      title="Weekly Net Positioning Change (momentum only - does not affect bias)"
    >
      {positive ? '▲' : '▼'} {positive ? '+' : ''}{pct.toFixed(2)}%
    </span>
  );
}

export default function CftcTab({ data }: Props) {
  const positions: Record<string, CftcPosition> = data?.positions || {};
  const entries = Object.entries(positions);

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
          Institutional long/short positioning with Long Ratio tiered bias · {entries.length} markets
        </p>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        {entries.slice(0, 4).map(([market, pos]) => {
          const lr = computeLongRatio(pos);
          const signal = getLongRatioSignal(lr);
          const weeklyPct = pos.weekly_change_pct ?? 0;
          return (
            <div key={market} className="card p-3">
              <div className="text-2xs text-gray-500 uppercase mb-1">{market}</div>
              <div className={`stat-value ${pos.net_speculative >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                {pos.net_speculative >= 0 ? '+' : ''}{(pos.net_speculative / 1000).toFixed(0)}K
              </div>
              {/* Overall Long Ratio bar — sentiment-colored */}
              <div className="flex items-center gap-2 mt-1">
                <div className="flex-1 bg-gray-700 rounded-full h-1.5">
                  <div
                    className={`h-1.5 rounded-full ${lr >= 50 ? 'bg-emerald-500' : 'bg-red-500'}`}
                    style={{ width: `${Math.min(lr, 100)}%` }}
                  />
                </div>
                <span className={`text-2xs font-mono ${signal.color}`}>{lr.toFixed(1)}%</span>
              </div>
              <div className="flex items-center justify-between mt-1">
                <div className="text-2xs text-gray-500">{signal.label}</div>
                {/* ΔW momentum badge — visual only, never flips bias */}
                <WeeklyChangeBadge pct={weeklyPct} />
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
              <th className="text-right py-2 px-3 text-gray-500 font-medium uppercase tracking-wider">Report Date</th>
              <th className="text-right py-2 px-3 text-gray-500 font-medium uppercase tracking-wider">Long Contracts</th>
              <th className="text-right py-2 px-3 text-gray-500 font-medium uppercase tracking-wider">Short Contracts</th>
              <th className="text-right py-2 px-3 text-gray-500 font-medium uppercase tracking-wider">Net Speculative</th>
              <th className="text-right py-2 px-3 text-gray-500 font-medium uppercase tracking-wider">Weekly ΔW</th>
              <th className="text-center py-2 px-3 text-gray-500 font-medium uppercase tracking-wider">Long Ratio</th>
              <th className="text-center py-2 px-3 text-gray-500 font-medium uppercase tracking-wider">Score</th>
              <th className="text-center py-2 px-3 text-gray-500 font-medium uppercase tracking-wider">Bias</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-dark-border">
            {entries.map(([market, pos]) => {
              const lr = computeLongRatio(pos);
              const signal = getLongRatioSignal(lr);
              const weeklyPct = pos.weekly_change_pct ?? 0;
              const score = pos.cftc_score ?? 5.0;
              return (
                <tr key={market} className="hover:bg-dark-card/50 transition-colors">
                  <td className="py-2 px-3 font-bold text-white">{market}</td>
                  <td className="py-2 px-3 text-right text-gray-400 font-mono">{pos.report_date}</td>
                  <td className="py-2 px-3 text-right text-emerald-400 font-mono">
                    {pos.noncomm_long.toLocaleString()}
                  </td>
                  <td className="py-2 px-3 text-right text-red-400 font-mono">
                    {pos.noncomm_short.toLocaleString()}
                  </td>
                  <td className={`py-2 px-3 text-right font-mono font-bold ${
                    pos.net_speculative >= 0 ? 'text-emerald-400' : 'text-red-400'
                  }`}>
                    {pos.net_speculative >= 0 ? '+' : ''}{pos.net_speculative.toLocaleString()}
                  </td>
                  {/* ΔW — visual momentum only, never flips the bias */}
                  <td className="py-2 px-3 text-right">
                    <WeeklyChangeBadge pct={weeklyPct} />
                  </td>
                  <td className="py-2 px-3 text-center">
                    <div className="flex items-center gap-2 justify-center">
                      <div className="w-16 bg-gray-700 rounded-full h-1.5">
                        <div
                          className={`h-1.5 rounded-full ${lr >= 50 ? 'bg-emerald-500' : 'bg-red-500'}`}
                          style={{ width: `${Math.min(lr, 100)}%` }}
                        />
                      </div>
                      <span className="font-mono text-gray-300">{lr.toFixed(1)}%</span>
                    </div>
                  </td>
                  <td className="py-2 px-3 text-center">
                    <span className={`font-mono font-bold ${signal.color}`}>{score.toFixed(1)}</span>
                  </td>
                  <td className="py-2 px-3 text-center">
                    <span className={`text-2xs px-2 py-0.5 rounded font-medium ${signal.bg} ${signal.color}`}>
                      {signal.label}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Institutional breakdown if available */}
      {entries.some(([_, pos]) => pos.asset_mgr_long !== undefined) && (
        <div className="mt-6 card p-4">
          <div className="card-header -mx-4 -mt-4 mb-3">Institutional Breakdown (Asset Managers vs Leveraged Funds)</div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-dark-border">
                  <th className="text-left py-2 pr-3 text-gray-500 font-medium">Market</th>
                  <th className="text-right py-2 px-3 text-gray-500 font-medium">AM Long</th>
                  <th className="text-right py-2 px-3 text-gray-500 font-medium">AM Short</th>
                  <th className="text-right py-2 px-3 text-gray-500 font-medium">LF Long</th>
                  <th className="text-right py-2 px-3 text-gray-500 font-medium">LF Short</th>
                  <th className="text-center py-2 pl-3 text-gray-500 font-medium">Smart Money</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-dark-border">
                {entries.filter(([_, pos]) => pos.asset_mgr_long !== undefined).map(([market, pos]) => {
                  const amNet = (pos.asset_mgr_long || 0) - (pos.asset_mgr_short || 0);
                  const lfNet = (pos.lev_funds_long || 0) - (pos.lev_funds_short || 0);
                  return (
                    <tr key={market}>
                      <td className="py-2 pr-3 font-bold text-white">{market}</td>
                      <td className="py-2 px-3 text-right text-emerald-400 font-mono">{(pos.asset_mgr_long || 0).toLocaleString()}</td>
                      <td className="py-2 px-3 text-right text-red-400 font-mono">{(pos.asset_mgr_short || 0).toLocaleString()}</td>
                      <td className="py-2 px-3 text-right text-emerald-400 font-mono">{(pos.lev_funds_long || 0).toLocaleString()}</td>
                      <td className="py-2 px-3 text-right text-red-400 font-mono">{(pos.lev_funds_short || 0).toLocaleString()}</td>
                      <td className={`py-2 pl-3 text-center font-mono font-bold ${amNet > 0 && lfNet > 0 ? 'text-emerald-400' : amNet < 0 && lfNet < 0 ? 'text-red-400' : 'text-gray-400'}`}>
                        {amNet > 0 && lfNet > 0 ? 'Long' : amNet < 0 && lfNet < 0 ? 'Short' : 'Mixed'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}