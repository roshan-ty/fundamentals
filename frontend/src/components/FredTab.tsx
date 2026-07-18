import React, { useMemo } from 'react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';

interface Props {
  data: any;
}

const FRED_SERIES_DISPLAY = [
  { id: 'GDPC1', name: 'Real GDP', color: '#10b981', unit: 'Billions USD' },
  { id: 'CPILFESL', name: 'Core CPI', color: '#3b82f6', unit: 'Index' },
  { id: 'PCEPILFE', name: 'Core PCE', color: '#8b5cf6', unit: 'Index' },
  { id: 'UNRATE', name: 'Unemployment Rate', color: '#f59e0b', unit: 'Percent' },
  { id: 'FEDFUNDS', name: 'Fed Funds Rate', color: '#ef4444', unit: 'Percent' },
  { id: 'DGS10', name: '10Y Treasury Yield', color: '#06b6d4', unit: 'Percent' },
  { id: 'DGS2', name: '2Y Treasury Yield', color: '#ec4899', unit: 'Percent' },
  { id: 'T10YIE', name: '10Y Breakeven Inflation', color: '#84cc16', unit: 'Percent' },
];

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-dark-card border border-dark-border rounded-lg p-3 text-xs shadow-xl">
      <p className="text-gray-400 mb-1">{label}</p>
      {payload.map((entry: any, i: number) => (
        <p key={i} style={{ color: entry.color }} className="font-mono font-medium">
          {entry.name}: {typeof entry.value === 'number' ? entry.value.toFixed(2) : entry.value}
        </p>
      ))}
    </div>
  );
};

export default function FredTab({ data }: Props) {
  const series = data?.series || {};

  const chartDataMap = useMemo(() => {
    const map: Record<string, any[]> = {};
    for (const meta of FRED_SERIES_DISPLAY) {
      const obs = series[meta.id];
      if (!obs || !obs.length) continue;
      // Limit to last 60 points for performance
      const points = obs.slice(0, 60).reverse();
      map[meta.id] = points.map((p: any) => ({
        date: p.date ? new Date(p.date).toLocaleDateString('en-US', { month: 'short', year: '2-digit' }) : '',
        value: p.value,
      }));
    }
    return map;
  }, [series]);

  const availableSeries = FRED_SERIES_DISPLAY.filter(s => chartDataMap[s.id]?.length > 0);

  if (availableSeries.length === 0) {
    return (
      <div className="text-center py-12 text-gray-500">
        No FRED data available. Run the data pipeline with a valid FRED_API_KEY.
      </div>
    );
  }

  return (
    <div>
      <div className="mb-4">
        <h2 className="text-sm font-semibold text-white">Federal Reserve Economic Data (FRED)</h2>
        <p className="text-2xs text-gray-500 mt-0.5">
          Historical macro-economic series from the Federal Reserve Bank of St. Louis · {availableSeries.length} series
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {availableSeries.map(meta => {
          const chartData = chartDataMap[meta.id];
          if (!chartData || chartData.length < 2) return null;

          const minVal = Math.min(...chartData.map(d => d.value));
          const maxVal = Math.max(...chartData.map(d => d.value));
          const padding = (maxVal - minVal) * 0.1 || 1;

          return (
            <div key={meta.id} className="card">
              <div className="card-header flex items-center justify-between">
                <span>{meta.name}</span>
                <span className="text-2xs text-gray-500">{meta.unit}</span>
              </div>
              <div className="p-3">
                <div className="text-2xs text-gray-500 mb-2">
                  Latest: <span className="font-mono text-white">
                    {chartData[chartData.length - 1].value.toFixed(2)}
                  </span>
                  {' · '}Min: {minVal.toFixed(2)} / Max: {maxVal.toFixed(2)}
                </div>
                <ResponsiveContainer width="100%" height={200}>
                  <LineChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                    <XAxis
                      dataKey="date"
                      tick={{ fill: '#6b7280', fontSize: 10 }}
                      tickLine={false}
                      axisLine={false}
                      interval="preserveStartEnd"
                    />
                    <YAxis
                      tick={{ fill: '#6b7280', fontSize: 10 }}
                      tickLine={false}
                      axisLine={false}
                      domain={[minVal - padding, maxVal + padding]}
                      tickFormatter={(v: number) => v.toFixed(1)}
                    />
                    <Tooltip content={<CustomTooltip />} />
                    <Line
                      type="monotone"
                      dataKey="value"
                      stroke={meta.color}
                      strokeWidth={2}
                      dot={false}
                      activeDot={{ r: 4, fill: meta.color }}
                      name={meta.name}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}