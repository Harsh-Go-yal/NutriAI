import React, { useEffect, useState } from 'react';
import { Flame, Loader2 } from 'lucide-react';
import { logCalendar } from '../services/api';

const DOW = ['M', 'T', 'W', 'T', 'F', 'S', 'S'];

/**
 * Compact five-week activity grid for the sidebar.
 *
 * Selecting a day does not expand here -- it raises the date so the parent can
 * open a full-width view. A day's meals, macros and micronutrients do not fit
 * legibly in a 248px column, and cramming them there was the wrong call.
 *
 * Intensity is scaled to the busiest day in the window rather than a fixed
 * calorie ceiling, so the pattern reads the same at 1400 or 3000 kcal.
 */
export default function LogCalendar({ selected, onSelectDay }) {
  const [days, setDays] = useState([]);
  const [streak, setStreak] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => { load(); }, []);

  // Re-read whenever the parent signals the log changed.
  useEffect(() => {
    const onChange = () => load();
    window.addEventListener('nutriai:log-changed', onChange);
    return () => window.removeEventListener('nutriai:log-changed', onChange);
  }, []);

  const load = () =>
    logCalendar()
      .then((d) => { setDays(d.days || []); setStreak(d.current_streak || 0); })
      .catch(() => {})
      .finally(() => setLoading(false));

  const peak = Math.max(...days.map((d) => d.calories || 0), 1);

  const shade = (day) => {
    if (!day.logged) return 'bg-white/[0.04] hover:bg-white/[0.08]';
    const ratio = (day.calories || 0) / peak;
    if (ratio > 0.75) return 'bg-emerald-500/85';
    if (ratio > 0.5) return 'bg-emerald-500/60';
    if (ratio > 0.25) return 'bg-emerald-500/40';
    return 'bg-emerald-500/25';
  };

  return (
    <div className="px-4 py-3">
      <div className="flex items-center justify-between mb-2.5">
        <span className="text-[10px] uppercase tracking-[0.12em] text-gray-600">
          Log history
        </span>
        {streak > 0 && (
          <span className="flex items-center gap-1 text-[11px] text-amber-500/90">
            <Flame className="w-3 h-3" strokeWidth={2} />{streak}d
          </span>
        )}
      </div>

      {loading ? (
        <div className="flex justify-center py-4">
          <Loader2 className="w-3.5 h-3.5 animate-spin text-gray-700" />
        </div>
      ) : (
        <>
          <div className="grid grid-cols-7 gap-[3px] mb-1">
            {DOW.map((d, i) => (
              <div key={i} className="text-[9px] text-gray-700 text-center">{d}</div>
            ))}
          </div>
          <div className="grid grid-cols-7 gap-[3px]">
            {days.map((day) => (
              <button
                key={day.date}
                onClick={() => onSelectDay?.(day.date)}
                title={`${day.date} — ${day.logged ? `${day.calories} kcal · ${day.entries} items` : 'nothing logged'}`}
                className={`aspect-square rounded-[3px] transition-all ${shade(day)} ${
                  day.is_today ? 'ring-1 ring-emerald-400/80' : ''
                } ${selected === day.date ? 'ring-1 ring-white' : ''}`}
              />
            ))}
          </div>
          <p className="mt-2.5 text-[10px] text-gray-700">
            Select a day to open it
          </p>
        </>
      )}
    </div>
  );
}
