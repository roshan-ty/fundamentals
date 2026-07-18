import React from 'react';

interface CalendarEvent {
  date: string;
  currency: string;
  event: string;
  forecast: number | null;
  actual: number | null;
  previous: number | null;
  impact: string;
  source: string;
}

interface Props {
  data: any;
}

export default function CalendarTab({ data }: Props) {
  const events: CalendarEvent[] = data?.events || [];

  if (!events.length) {
    return (
      <div className="text-center py-12 text-gray-500">
        <p>No calendar events available. Run the data pipeline to fetch the latest economic calendar.</p>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-sm font-semibold text-white">Economic Calendar</h2>
          <p className="text-2xs text-gray-500 mt-0.5">{events.length} events · Sorted by date</p>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-dark-border">
              <th className="text-left py-2 px-3 text-gray-500 font-medium uppercase tracking-wider">Date</th>
              <th className="text-left py-2 px-3 text-gray-500 font-medium uppercase tracking-wider">Currency</th>
              <th className="text-left py-2 px-3 text-gray-500 font-medium uppercase tracking-wider">Event</th>
              <th className="text-right py-2 px-3 text-gray-500 font-medium uppercase tracking-wider">Forecast</th>
              <th className="text-right py-2 px-3 text-gray-500 font-medium uppercase tracking-wider">Actual</th>
              <th className="text-right py-2 px-3 text-gray-500 font-medium uppercase tracking-wider">Previous</th>
              <th className="text-center py-2 px-3 text-gray-500 font-medium uppercase tracking-wider">Surprise</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-dark-border">
            {events.map((ev, i) => {
              const surprise = ev.actual !== null && ev.forecast !== null && ev.forecast !== 0
                ? ((ev.actual - ev.forecast) / Math.abs(ev.forecast) * 100).toFixed(1)
                : null;
              const surpriseNum = surprise ? parseFloat(surprise) : 0;
              const isBeat = surpriseNum > 0;
              const isMiss = surpriseNum < 0;

              return (
                <tr key={i} className="hover:bg-dark-card/50 transition-colors">
                  <td className="py-2 px-3 text-gray-400 font-mono whitespace-nowrap">
                    {ev.date ? new Date(ev.date).toLocaleDateString('en-US', {
                      month: 'short', day: 'numeric', year: 'numeric'
                    }) : '—'}
                  </td>
                  <td className="py-2 px-3">
                    <span className="font-bold text-white">{ev.currency || '—'}</span>
                  </td>
                  <td className="py-2 px-3 text-gray-300 max-w-[250px] truncate" title={ev.event}>
                    {ev.event}
                  </td>
                  <td className="py-2 px-3 text-right text-gray-400 font-mono">
                    {ev.forecast?.toFixed(1) ?? '—'}
                  </td>
                  <td className={`py-2 px-3 text-right font-mono font-bold ${
                    isBeat ? 'text-emerald-400' : isMiss ? 'text-red-400' : 'text-gray-300'
                  }`}>
                    {ev.actual?.toFixed(1) ?? '—'}
                  </td>
                  <td className="py-2 px-3 text-right text-gray-500 font-mono">
                    {ev.previous?.toFixed(1) ?? '—'}
                  </td>
                  <td className="py-2 px-3 text-center">
                    {surprise ? (
                      <span className={`text-2xs px-2 py-0.5 rounded font-medium ${
                        isBeat ? 'bg-emerald-900/30 text-emerald-400' :
                        isMiss ? 'bg-red-900/30 text-red-400' :
                        'bg-gray-700/30 text-gray-400'
                      }`}>
                        {isBeat ? '+' : ''}{surprise}%
                      </span>
                    ) : (
                      <span className="text-gray-600">—</span>
                    )}
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