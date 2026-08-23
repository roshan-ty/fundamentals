import React from 'react';

interface Props {
  score: number;
}

// Map a 1-10 score to a directional bias label
function biasLabel(score: number): string {
  if (score >= 7.0) return 'Strongly Bullish';
  if (score >= 6.0) return 'Bullish';
  if (score >= 4.1) return 'Neutral';
  if (score >= 2.1) return 'Bearish';
  return 'Strongly Bearish';
}

// Color-coded text class based on score
function scoreColor(score: number): string {
  if (score >= 7.0) return 'text-emerald-400';
  if (score >= 6.0) return 'text-emerald-300';
  if (score >= 4.1) return 'text-gray-300';
  if (score >= 2.1) return 'text-red-300';
  return 'text-red-400';
}

export default function HorizontalBiasMeter({ score }: Props) {
  // Clamp score to [1, 10]
  const clamped = Math.max(1.0, Math.min(10.0, score));
  // Left position % = ((score - 1.0) / 9.0) * 100
  const leftPct = ((clamped - 1.0) / 9.0) * 100;

  // Segment tick positions at 1, 3, 5, 7, 10
  const ticks = [1, 3, 5, 7, 10].map(v => ({
    value: v,
    left: ((v - 1.0) / 9.0) * 100,
  }));

  const label = biasLabel(clamped);
  const color = scoreColor(clamped);

  return (
    <div className="w-full">
      {/* Score display */}
      <div className="flex items-baseline justify-between mb-2">
        <span className={`text-2xl font-bold font-mono ${color}`}>
          {clamped.toFixed(1)}
          <span className="text-sm text-gray-500 font-normal"> / 10</span>
        </span>
        <span className={`text-xs font-semibold uppercase tracking-wider ${color}`}>
          {label}
        </span>
      </div>

      {/* Track */}
      <div className="relative h-3 rounded-full overflow-visible"
        style={{
          background: 'linear-gradient(90deg, #EF4444 0%, #64748B 50%, #22C55E 100%)',
        }}
      >
        {/* Segment ticks */}
        {ticks.map(t => (
          <div
            key={t.value}
            className="absolute top-0 h-full w-px bg-black/40"
            style={{ left: `${t.left}%` }}
          />
        ))}

        {/* Glowing needle */}
        <div
          className="absolute top-1/2 -translate-y-1/2 w-1.5 h-6 rounded-full bg-white shadow-[0_0_8px_rgba(255,255,255,0.9)]"
          style={{
            left: `${leftPct}%`,
            transform: 'translate(-50%, -50%)',
            transition: 'left 0.5s cubic-bezier(0.4, 0, 0.2, 1)',
          }}
        />
      </div>

      {/* Scale labels */}
      <div className="flex justify-between mt-1 text-2xs text-gray-500 font-mono">
        <span>1.0</span>
        <span>3.0</span>
        <span>5.0</span>
        <span>7.0</span>
        <span>10.0</span>
      </div>
    </div>
  );
}