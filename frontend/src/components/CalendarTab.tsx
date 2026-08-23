import React, { useMemo, useState } from 'react';

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
  // Support both the bare-array format (scripts/calendar_scraper.py) and the
  // legacy wrapped format ({ events: [...] }).
  const events: CalendarEvent[] = Array.isArray(data) ? data : (data?.events || []);
  const [showOnlyReleased, setShowOnlyReleased] = useState(false);

  const filteredEvents = useMemo(() => {
    if (!showOnlyReleased) return events;
    return events.filter(ev => ev.actual !== null && ev.actual !== undefined);
  }, [events, showOnlyReleased]);

  const releasedCount = events.filter(ev => ev.actual !== null && ev.actual !== undefined).length;

  if (!events.length) {
    return (
      <div className="text-center py-12 text-gray-500">
        <p>No calendar events available.</p>
      </div>
    );
  }

  const getSurprise = (ev: CalendarEvent): number | null => {
    if (ev.actual === null || ev.forecast === null) return null;
    if (ev.forecast === 0) {
      return ev.actual !== 0 ? (ev.actual > 0 ? 100 : -100) : 0;
    }
    return ((ev.actual - ev.forecast) / Math.abs(ev.forecast)) * 100;
  };

  const getSurpriseLabel = (surprise: number | null): string => {
    if (surprise === null) return '—';
    if (surprise > 0) return `+${surprise.toFixed(1)}%`;
    return `${surprise.toFixed(1)}%`;
  };

  const getSurpriseColor = (surprise: number | null): string => {
    if (surprise === null) return 'text-gray-600';
    if (surprise > 0) return 'text-emerald-400';
    if (surprise < 0) return 'text-red-400';
    return 'text-gray-400';
  };

  const getSurpriseBadge = (surprise: number | null): string => {
    if (surprise === null) return 'bg-gray-700/30 text-gray-400';
    if (surprise > 0) return 'bg-emerald-900/30 text-emerald-400';
    if (surprise < 0) return 'bg-red-900/30 text-red-400';
    return 'bg-gray-700/30 text-gray-400';
  };

  const getImpactBadge = (impact: string): string => {
    const i = (impact || 'low').toLowerCase();
    if (i === 'high') return 'bg-red-900/40 text-red-400 border-red-700/40';
    if (i === 'medium' || i === 'med') return 'bg-yellow-900/40 text-yellow-400 border-yellow-700/40';
    return 'bg-gray-700/40 text-gray-400 border-gray-600/40';
  };

  return (
    <div>
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-4">
        <div>
          <h2 className="text-sm font-semibold text-white">Economic Calendar</h2>
          <p className="text-2xs text-gray-500 mt-0.5">
            {events.length} events · {releasedCount} released with actual data
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowOnlyReleased(!showOnlyReleased)}
            className={`text-2xs px-3 py-1.5 rounded border transition-colors ${
              showOnlyReleased
                ? 'bg-emerald-900/40 text-emerald-400 border-emerald-700/40'
                : 'bg-dark-border text-gray-400 border-dark-border hover:text-white'
            }`}
          >
            {showOnlyReleased ? '✓ Showing Released Only' : 'Show Released Only'}
          </button>
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
              <th className="text-center py-2 px-3 text-gray-500 font-medium uppercase tracking-wider">Impact</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-dark-border">
            {filteredEvents.map((ev, i) => {
              const surprise = getSurprise(ev);
              const isBeat = surprise !== null && surprise > 0;
              const isMiss = surprise !== null && surprise < 0;
              const hasActual = ev.actual !== null && ev.actual !== undefined;

              return (
                <tr key={i} className={`hover:bg-dark-card/50 transition-colors ${hasActual ? 'bg-dark-card/20' : ''}`}>
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
                    hasActual
                      ? isBeat ? 'text-emerald-400' : isMiss ? 'text-red-400' : 'text-gray-300'
                      : 'text-gray-600'
                  }`}>
                    {hasActual ? ev.actual?.toFixed(1) : '—'}
                  </td>
                  <td className="py-2 px-3 text-right text-gray-500 font-mono">
                    {ev.previous?.toFixed(1) ?? '—'}
                  </td>
                  <td className="py-2 px-3 text-center">
                    {hasActual && surprise !== null ? (
                      <span className={`text-2xs px-2 py-0.5 rounded font-medium ${getSurpriseBadge(surprise)}`}>
                        {getSurpriseLabel(surprise)}
                      </span>
                    ) : (
                      <span className="text-gray-600">—</span>
                    )}
                  </td>
                  <td className="py-2 px-3 text-center">
                    <span className={`text-2xs px-2 py-0.5 rounded border ${getImpactBadge(ev.impact)}`}>
                      {(ev.impact || 'low').toUpperCase()}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {filteredEvents.length === 0 && (
        <div className="text-center py-8 text-gray-500 text-sm">
          No released events with actual data yet. Check back after the next economic data release.
        </div>
      )}
    </div>
  );
}