import React from 'react';

interface Props {
  score: number;
  size?: number;
}

interface Point {
  x: number;
  y: number;
}

const toRad = (deg: number) => (deg * Math.PI) / 180;

export default function GaugeChart({ score, size = 180 }: Props) {
  // Normalize score (1-10) to 0-1
  const normalized = Math.max(0, Math.min(1, (score - 1) / 9));
  const scoreAngle = normalized * 180; // 0 at score=1 → 180 at score=10

  // Gauge geometry
  const width = size;
  const height = size * 0.55;
  const cx = width / 2;
  const cy = height * 0.92; // baseline sits near bottom so the semicircle fits
  const r = size * 0.38;
  const strokeWidth = size * 0.07;

  const startDeg = 180; // left side (score = 1)
  const endDeg = 0;     // right side (score = 10)

  /**
   * Returns the (x, y) coordinates of a point on a circle of given radius
   * centered at (cx, cy) at the specified degree angle.
   *
   * Angle convention: 180° = left, 90° = top, 0° = right.
   */
  const pointOnArc = (deg: number, radius: number): Point => {
    const rad = toRad(deg);
    return {
      x: cx + radius * Math.cos(rad),
      y: cy - radius * Math.sin(rad),
    };
  };

  /**
   * SVG arc path sweeping counter-clockwise from `start` degrees down to `end`
   * degrees over the TOP of the gauge (large-arc = 0 for ≤ 180° spans, sweep = 0).
   *
   * sweep = 0 (counter-clockwise) draws the arc over the top:
   *   180° (left) → 90° (top) → 0° (right)
   */
  const arcPath = (start: number, end: number): string => {
    const p1 = pointOnArc(start, r);
    const p2 = pointOnArc(end, r);
    const large = Math.abs(end - start) > 180 ? 1 : 0;
    return `M ${p1.x} ${p1.y} A ${r} ${r} 0 ${large} 0 ${p2.x} ${p2.y}`;
  };

  // Value arc: from left (180°) to the needle position (180° - scoreAngle)
  const needleDeg = 180 - scoreAngle;

  // Color based on score
  const color = score >= 7 ? '#10b981' : score >= 5 ? '#3b82f6' :
                score >= 3 ? '#f59e0b' : '#ef4444';

  // Tick marks for values 1..10 — 18° apart
  const ticks = Array.from({ length: 10 }, (_, i) => {
    const deg = 180 - (i + 1) * 18;
    const outer = pointOnArc(deg, r + strokeWidth / 2 + 3);
    const inner = pointOnArc(deg, r + strokeWidth / 2 + 7);
    return { outer, inner, value: i + 1 };
  });

  const label1 = pointOnArc(180, r + 12);
  const label10 = pointOnArc(0, r + 12);

  // Needle rotation: at score=1 the needle points left (180°), at score=10 it
  // points right (0°). We rotate the needle group around the pivot (cx, cy).
  // The needle is drawn pointing straight up (gauge angle 90°). SVG rotation is
  // clockwise-positive, while the gauge angle increases counter-clockwise, so we
  // rotate by (90 - needleDeg) to align the needle with the target angle.
  const needleRotation = 90 - needleDeg;

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
      {/* Background arc */}
      <path
        d={arcPath(startDeg, endDeg)}
        fill="none"
        stroke="#334155"
        strokeWidth={strokeWidth}
        strokeLinecap="round"
      />
      {/* Value arc (from left edge to current needle position) */}
      <path
        d={arcPath(startDeg, needleDeg)}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        style={{ transition: 'all 0.5s ease' }}
      />
      {/* Tick marks */}
      {ticks.map(tick => (
        <line
          key={tick.value}
          x1={tick.inner.x}
          y1={tick.inner.y}
          x2={tick.outer.x}
          y2={tick.outer.y}
          stroke="#475569"
          strokeWidth={1.5}
          strokeLinecap="round"
        />
      ))}
      {/* Needle — rotated around the pivot (cx, cy) for a clean, consistent pivot */}
      <g
        style={{
          transform: `rotate(${needleRotation}deg)`,
          transformOrigin: `${cx}px ${cy}px`,
          transition: 'transform 0.5s ease',
        }}
      >
        <line
          x1={cx}
          y1={cy}
          x2={cx}
          y2={cy - r}
          stroke={color}
          strokeWidth={2}
          strokeLinecap="round"
        />
      </g>
      {/* Center pivot */}
      <circle cx={cx} cy={cy} r={4} fill={color} />
      {/* Labels */}
      <text
        x={label1.x}
        y={label1.y + 3}
        fill="#6b7280"
        fontSize={size * 0.045}
        textAnchor="middle"
      >
        1
      </text>
      <text
        x={label10.x}
        y={label10.y + 3}
        fill="#6b7280"
        fontSize={size * 0.045}
        textAnchor="middle"
      >
        10
      </text>
    </svg>
  );
}