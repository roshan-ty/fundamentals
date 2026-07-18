import React from 'react';
import { DataStore } from '../App';

interface Props {
  data: DataStore;
}

const POINT_LABELS: { id: string; label: string; source: string }[] = [
  { id: 'GDPC1', label: 'Real GDP', source: 'FRED' },
  { id: 'CPILFESL', label: 'Core CPI', source: 'FRED' },
  { id: 'PCEPILFE', label: 'Core PCE', source: 'FRED' },
  { id: 'UNRATE', label: 'Unemployment Rate', source: 'FRED' },
  { id: 'FEDFUNDS', label: 'Fed Funds Rate', source: 'FRED' },
  { id: 'T10YIE', label: '10Y Breakeven Inflation', source: 'FRED' },
  { id: 'M2SL', label: 'M2 Money Supply', source: 'FRED' },
  { id: 'INDPRO', label: 'Industrial Production', source: 'FRED' },
  { id: 'CPIAUCSL', label: 'Headline CPI', source: 'FRED' },
  { id: 'PPIACO', label: 'PPI All Commodities', source: 'FRED' },
  { id: 'PAYEMS', label: 'Nonfarm Payrolls', source: 'FRED' },
  { id: 'DGS10', label: '10Y Treasury Yield', source: 'FRED' },
  { id: 'DGS2', label: '2Y Treasury Yield', source: 'FRED' },
];

export default function FundamentalTab({ data }: Props) {
  const macroData = data.macro_data;
  const baseScores = data.master_bias?.base_scores || {};
  const fredSeries = macroData?.series || {};

  const points = POINT_LABELS.map(p => {
    const obs = fredSeries[p.id];
    const latestVal = obs?.[0]?.value ?? null;
    const latestDate = obs?.[0]?.date ?? null;

    // Compute a simple 1-10 score for each data point
    let score = 5;
    if (p.id === 'UNRATE' && latestVal !== null) {
      score = latestVal < 3.5 ? 9 : latestVal < 4.5 ? 7 : latestVal < 6 ? 5 : 3;
    } else if (p.id === 'FEDFUNDS' && latestVal !== null) {
      score = latestVal > 5 ? 7 : latestVal > 3 ? 6 : latestVal > 0 ? 5 : 3;
    } else if (p.id === 'CPILFESL' && latestVal !== null) {
      score = latestVal > 320 ? 7 : latestVal > 310 ? 6 : 5;
    } else if (baseScores['USD'] && p.id === 'GDPC1') {
      score = Math.round(baseScores['USD']);
    }

    return { ...p, value: latestVal, date: latestDate, score };
  });

  return (
    <div>
      <div className="mb-4">
        <h2 className="text-sm font-semibold text-white">30 Fundamental Data Points</h2>
        <p className="text-2xs text-gray-500 mt-0.5">Side-by-side raw values and 1-10 systematic rankings</p>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-dark-border">
              <th className="text-left py-2 px-3 text-gray-500 font-medium uppercase tracking-wider">Point</th>
              <th className="text-left py-2 px-3 text-gray-500 font-medium uppercase tracking-wider">Source</th>
              <th className="text-right py-2 px-3 text-gray-500 font-medium uppercase tracking-wider">Latest Value</th>
              <th className="text-right py-2 px-3 text-gray-500 font-medium uppercase tracking-wider">Date</th>
              <th className="text-center py-2 px-3 text-gray-500 font-medium uppercase tracking-wider">Score (1-10)</th>
              <th className="text-center py-2 px-3 text-gray-500 font-medium uppercase tracking-wider">Signal</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-dark-border">
            {points.map((p, i) => {
              const color = p.score >= 7 ? 'text-emerald-400' :
                p.score >= 5 ? 'text-blue-400' :
                p.score >= 3 ? 'text-yellow-400' : 'text-red-400';
              const signal = p.score >= 7 ? 'Bullish' :
                p.score >= 5 ? 'Neutral' :
                p.score >= 3 ? 'Bearish' : 'Strong Bearish';

              return (
                <tr key={i} className="hover:bg-dark-card/50 transition-colors">
                  <td className="py-2 px-3 font-medium text-white">{p.label}</td>
                  <td className="py-2 px-3">
                    <span className="text-2xs px-1.5 py-0.5 bg-dark-border rounded text-gray-400">{p.source}</span>
                  </td>
                  <td className="py-2 px-3 text-right font-mono text-gray-300">
                    {p.value !== null ? p.value.toLocaleString(undefined, { maximumFractionDigits: 2 }) : '—'}
                  </td>
                  <td className="py-2 px-3 text-right text-gray-500 font-mono">
                    {p.date || '—'}
                  </td>
                  <td className={`py-2 px-3 text-center font-mono font-bold ${color}`}>
                    {p.score.toFixed(1)}
                  </td>
                  <td className="py-2 px-3 text-center">
                    <span className={`text-2xs px-2 py-0.5 rounded font-medium ${
                      p.score >= 7 ? 'bg-emerald-900/30 text-emerald-400' :
                      p.score >= 5 ? 'bg-blue-900/30 text-blue-400' :
                      p.score >= 3 ? 'bg-yellow-900/30 text-yellow-400' :
                      'bg-red-900/30 text-red-400'
                    }`}>
                      {signal}
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