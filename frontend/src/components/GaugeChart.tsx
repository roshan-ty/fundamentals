import React from 'react';

interface Props {
  score: number;
  size?: number;
}

export default function GaugeChart({ score, size = 180 }: Props) {
  // Normalize score to 0-1 range
  const normalized = Math.max(0, Math.min(1, (score - 1) / 9));
  const angle = normalized * 180; // 0 to 180 degrees

  // Gauge arc parameters
  const cx = size / 2;
  const cy = size / 2;
  const r = size * 0.38;
  const strokeWidth = size * 0.08;

  const startAngle = 180;
  const endAngle = 0;

  const toRad = (deg: number) => (deg * Math.PI) / 180;

  // Arc path
  const arcPath = (start: number, end: number) => {
    const x1 = cx + r * Math.cos(toRad(start));
    const y1 = cy - r * Math.sin(toRad(start));
    const x2 = cx + r * Math.cos(toRad(end));
    const y2 = cy - r * Math.sin(toRad(end));
    const large = Math.abs(end - start) > 180 ? 1 : 0;
    return `M ${x1} ${y1} A ${r} ${r} 0 ${large} 0 ${x2} ${y2}`;
  };

  // Needle position
  const needleAngle = startAngle - angle;
  const nx = cx + r * 0.7 * Math.cos(toRad(needleAngle));
  const ny = cy - r * 0.7 * Math.sin(toRad(needleAngle));

  // Color based on score
  const color = score >= 7 ? '#10b981' : score >= 5 ? '#3b82f6' :
                score >= 3 ? '#f59e0b' : '#ef4444';

  return (
    <svg width={size} height={size * 0.6} viewBox={`0 0 ${size} ${size * 0.65}`}>
      {/* Background arc */}
      <path
        d={arcPath(startAngle, endAngle)}
        fill="none"
        stroke="#334155"
        strokeWidth={strokeWidth}
        strokeLinecap="round"
      />
      {/* Value arc */}
      <path
        d={arcPath(startAngle, startAngle - angle)}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        style={{ transition: 'all 0.5s ease' }}
      />
      {/* Needle */}
      <line
        x1={cx}
        y1={cy}
        x2={nx}
        y2={ny}
        stroke={color}
        strokeWidth={2}
        strokeLinecap="round"
      />
      {/* Center dot */}
      <circle cx={cx} cy={cy} r={4} fill={color} />
      {/* Labels */}
      <text x={cx - r - 5} y={cy + r * 0.3} fill="#6b7280" fontSize={size * 0.045} textAnchor="start">
        1
      </text>
      <text x={cx + r + 5} y={cy + r * 0.3} fill="#6b7280" fontSize={size * 0.045} textAnchor="end">
        10
      </text>
    </svg>
  );
}