import React from 'react';
import { TrendingUp, DollarSign, BarChart3, Users, Target } from 'lucide-react';
import { DataStore } from '../App';
import GaugeChart from './GaugeChart';

interface Props {
  data: DataStore;
}

export default function HomeTab({ data }: Props) {
  const masterBias = data.master_bias;
  const macroData = data.macro_data;
  const aiInsights = data.ai_insights;

  const baseScores = masterBias?.base_scores || {};
  const usdScore = baseScores['USD'] || 5.0;
  const pairs = masterBias?.pairs || [];
  const summary = masterBias?.summary || {};

  const bullishCount = summary.bullish_count || 0;
  const bearishCount = summary.bearish_count || 0;
  const neutralCount = summary.neutral_count || 0;
  const totalPairs = masterBias?.total_pairs || 0;

  // Latest FRED values
  const fredSeries = macroData?.series || {};
  const getFredVal = (id: string) => {
    const obs = fredSeries[id];
    return obs?.[0]?.value ?? null;
  };

  const gdpVal = getFredVal('GDPC1');
  const cpiVal = getFredVal('CPILFESL');
  const unrateVal = getFredVal('UNRATE');
  const fedFundsVal = getFredVal('FEDFUNDS');

  // Score breakdown
  const scoreItems = [
    { label: 'Macro Health', score: usdScore },
    { label: 'Inflation', score: cpiVal ? (cpiVal > 320 ? 7 : cpiVal > 310 ? 6 : 5) : 5 },
    { label: 'Labor Market', score: unrateVal ? (unrateVal < 4 ? 8 : unrateVal < 5 ? 6 : 4) : 5 },
    { label: 'Rate Environment', score: fedFundsVal ? (fedFundsVal > 5 ? 7 : fedFundsVal > 3 ? 6 : fedFundsVal > 0 ? 5 : 3) : 5 },
  ];

  return (
    <div className="space-y-6">
      {/* ═══ Header Stats ═══ */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="card p-3">
          <div className="flex items-center gap-2 mb-1">
            <DollarSign size={14} className="text-emerald-400" />
            <span className="text-2xs text-gray-500 uppercase">GDP</span>
          </div>
          <div className="stat-value text-emerald-400">
            {gdpVal ? `$${(gdpVal / 1000).toFixed(1)}T` : '—'}
          </div>
        </div>
        <div className="card p-3">
          <div className="flex items-center gap-2 mb-1">
            <BarChart3 size={14} className="text-blue-400" />
            <span className="text-2xs text-gray-500 uppercase">Core CPI</span>
          </div>
          <div className="stat-value text-blue-400">
            {cpiVal ? cpiVal.toFixed(1) : '—'}
          </div>
        </div>
        <div className="card p-3">
          <div className="flex items-center gap-2 mb-1">
            <Users size={14} className="text-purple-400" />
            <span className="text-2xs text-gray-500 uppercase">Unemployment</span>
          </div>
          <div className="stat-value text-purple-400">
            {unrateVal ? `${unrateVal.toFixed(1)}%` : '—'}
          </div>
        </div>
        <div className="card p-3">
          <div className="flex items-center gap-2 mb-1">
            <Target size={14} className="text-orange-400" />
            <span className="text-2xs text-gray-500 uppercase">Fed Funds</span>
          </div>
          <div className="stat-value text-orange-400">
            {fedFundsVal ? `${fedFundsVal.toFixed(2)}%` : '—'}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* ═══ USD Bias Gauge ═══ */}
        <div className="card">
          <div className="card-header">USD Fundamental Bias Score</div>
          <div className="p-4 flex flex-col items-center">
            <GaugeChart score={usdScore} size={200} />
            <div className="mt-3 text-center">
              <span className={`text-lg font-bold font-mono ${
                usdScore >= 6 ? 'text-emerald-400' : usdScore <= 4 ? 'text-red-400' : 'text-gray-400'
              }`}>
                {usdScore.toFixed(1)} / 10
              </span>
              <div className="text-xs text-gray-500 mt-1">
                {usdScore >= 7 ? 'Strongly Bullish' : usdScore >= 6 ? 'Bullish' :
                 usdScore >= 4.1 ? 'Neutral' : usdScore >= 2.1 ? 'Bearish' : 'Strongly Bearish'}
              </div>
            </div>
          </div>
        </div>

        {/* ═══ Score Breakdown Bars ═══ */}
        <div className="card">
          <div className="card-header">Component Scores Breakdown</div>
          <div className="p-4 space-y-4">
            {scoreItems.map(item => {
              const pct = (item.score / 10) * 100;
              const color = item.score >= 7 ? 'bg-emerald-500' :
                item.score >= 5 ? 'bg-blue-500' :
                item.score >= 3 ? 'bg-yellow-500' : 'bg-red-500';
              return (
                <div key={item.label}>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-gray-400">{item.label}</span>
                    <span className="font-mono font-medium">{item.score.toFixed(1)}</span>
                  </div>
                  <div className="w-full bg-gray-700 rounded-full h-2">
                    <div className={`h-2 rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* ═══ Market Breadth Summary ═══ */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div className="card p-3 text-center">
          <div className="stat-value text-emerald-400">{bullishCount}</div>
          <div className="stat-label">Bullish Signals</div>
          <div className="text-2xs text-gray-600">{totalPairs > 0 ? `${(bullishCount / totalPairs * 100).toFixed(0)}% of total` : ''}</div>
        </div>
        <div className="card p-3 text-center">
          <div className="stat-value text-gray-400">{neutralCount}</div>
          <div className="stat-label">Neutral</div>
        </div>
        <div className="card p-3 text-center">
          <div className="stat-value text-red-400">{bearishCount}</div>
          <div className="stat-label">Bearish Signals</div>
          <div className="text-2xs text-gray-600">{totalPairs > 0 ? `${(bearishCount / totalPairs * 100).toFixed(0)}% of total` : ''}</div>
        </div>
      </div>

      {/* ═══ AI Insights ═══ */}
      {aiInsights?.analysis && (
        <div className="card">
          <div className="card-header flex items-center gap-2">
            <BarChart3 size={14} />
            AI Macro Analysis
          </div>
          <div className="p-4">
            <div className="text-sm text-gray-300 leading-relaxed whitespace-pre-wrap font-mono text-[13px]">
              {aiInsights.analysis}
            </div>
            <div className="mt-3 text-2xs text-gray-600">
              Generated: {aiInsights.generated_at ? new Date(aiInsights.generated_at).toLocaleString() : 'N/A'}
              {aiInsights.provider && ` · Source: ${aiInsights.provider}`}
            </div>
          </div>
        </div>
      )}

      {/* ═══ Extreme Setups ═══ */}
      {masterBias?.extreme_setups && masterBias.extreme_setups.length > 0 && (
        <div className="card">
          <div className="card-header flex items-center gap-2">
            <Target size={14} />
            Extreme Setups ({masterBias.extreme_setups.length})
          </div>
          <div className="divide-y divide-dark-border">
            {masterBias.extreme_setups.slice(0, 8).map((setup: any, i: number) => (
              <div key={i} className="px-4 py-2.5 flex items-center justify-between">
                <span className="text-sm font-medium">{setup.name}</span>
                <div className="flex items-center gap-3">
                  <span className={`text-xs font-mono font-bold ${
                    setup.combined_bias >= 8 ? 'text-emerald-400' : 'text-red-400'
                  }`}>
                    {setup.combined_bias.toFixed(1)}
                  </span>
                  <span className={`text-2xs px-2 py-0.5 rounded ${
                    setup.combined_bias >= 8 ? 'bg-emerald-900/30 text-emerald-400' : 'bg-red-900/30 text-red-400'
                  }`}>
                    {setup.combined_bias >= 8 ? 'LONG' : 'SHORT'}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}