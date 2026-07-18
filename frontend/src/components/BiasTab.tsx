import React, { useState, useMemo } from 'react';
import { Search, X, ChevronDown, ChevronUp } from 'lucide-react';

interface PairBias {
  name: string;
  asset_class: string;
  base_asset: string;
  quote_asset: string;
  base_score: number;
  quote_score: number;
  combined_bias: number;
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

  // Detail Modal
  const renderModal = () => {
    if (!selectedPair) return null;
    const p = selectedPair;

    return (
      <div className="modal-overlay" onClick={() => setSelectedPair(null)}>
        <div className="modal-content" onClick={e => e.stopPropagation()}>
          <div className="flex items-center justify-between p-4 border-b border-dark-border">
            <h3 className="text-sm font-bold text-white">{p.name}</h3>
            <button onClick={() => setSelectedPair(null)} className="text-gray-400 hover:text-white">
              <X size={18} />
            </button>
          </div>
          <div className="p-4 space-y-4">
            {/* Asset class */}
            <div className="flex items-center gap-2 text-xs text-gray-400">
              <span className="px-2 py-0.5 bg-dark-border rounded">{p.asset_class}</span>
              <span>{p.base_asset} / {p.quote_asset}</span>
            </div>

            {/* Score card */}
            <div className="grid grid-cols-3 gap-3">
              <div className="card p-3 text-center">
                <div className="text-2xs text-gray-500 uppercase mb-1">Base Score</div>
                <div className={`text-lg font-bold font-mono ${getScoreColor(p.base_score)}`}>
                  {p.base_score.toFixed(1)}
                </div>
                <div className="text-2xs text-gray-600">{p.base_asset}</div>
              </div>
              <div className="card p-3 text-center">
                <div className="text-2xs text-gray-500 uppercase mb-1">Quote Score</div>
                <div className={`text-lg font-bold font-mono ${getScoreColor(p.quote_score)}`}>
                  {p.quote_score.toFixed(1)}
                </div>
                <div className="text-2xs text-gray-600">{p.quote_asset || 'N/A'}</div>
              </div>
              <div className="card p-3 text-center">
                <div className="text-2xs text-gray-500 uppercase mb-1">Combined Bias</div>
                <div className={`text-lg font-bold font-mono ${getScoreColor(p.combined_bias)}`}>
                  {p.combined_bias.toFixed(1)}
                </div>
                <div className={`text-2xs ${getBadge(p.direction)} px-1.5 py-0.5 rounded inline-block mt-1`}>
                  {p.direction}
                </div>
              </div>
            </div>

            {/* Formula breakdown */}
            <div className="card p-3">
              <div className="text-2xs text-gray-500 uppercase mb-2">Scoring Formula</div>
              <div className="text-xs font-mono text-gray-300">
                Pair Bias = 5 + (Base Score - Quote Score)
              </div>
              <div className="text-xs font-mono text-gray-400 mt-1">
                = 5 + ({p.base_score.toFixed(1)} - {p.quote_score.toFixed(1)}) = {p.combined_bias.toFixed(1)}
              </div>
            </div>

            {/* Base scores for this asset */}
            <div className="card p-3">
              <div className="text-2xs text-gray-500 uppercase mb-2">Underlying Asset Scores</div>
              <div className="space-y-1 text-xs">
                {Object.entries(baseScores)
                  .filter(([key]) => key === p.base_asset || key === p.quote_asset)
                  .map(([key, val]) => (
                    <div key={key} className="flex justify-between">
                      <span className="text-gray-400">{key}</span>
                      <span className={`font-mono font-medium ${getScoreColor(val)}`}>
                        {val.toFixed(2)}
                      </span>
                    </div>
                  ))}
              </div>
            </div>

            {/* All base scores reference */}
            <details className="card">
              <summary className="px-3 py-2 text-2xs text-gray-500 cursor-pointer hover:text-gray-300">
                All Base Asset Scores
              </summary>
              <div className="p-3 grid grid-cols-2 sm:grid-cols-3 gap-1 text-xs">
                {Object.entries(baseScores).map(([key, val]) => (
                  <div key={key} className="flex justify-between">
                    <span className="text-gray-400">{key}</span>
                    <span className={`font-mono ${getScoreColor(val)}`}>{val.toFixed(2)}</span>
                  </div>
                ))}
              </div>
            </details>
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
          <p className="text-2xs text-gray-500 mt-0.5">{allPairs.length} pairs · Sorted by strength</p>
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
          No pair data available. Run the data pipeline to generate scores.
        </div>
      )}

      {renderModal()}
    </div>
  );
}