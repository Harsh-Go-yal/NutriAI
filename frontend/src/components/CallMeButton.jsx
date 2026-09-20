import React, { useEffect, useState } from 'react';
import { Phone, PhoneCall, Loader2, Check, AlertTriangle } from 'lucide-react';
import { placeCall, callSchedule } from '../services/api';

const SLOTS = ['breakfast', 'lunch', 'snack', 'dinner'];

/** Slot the current clock falls into, mirroring the server's own windows. */
function slotNow() {
  const h = new Date().getHours();
  if (h >= 4 && h < 11) return 'breakfast';
  if (h >= 11 && h < 16) return 'lunch';
  if (h >= 16 && h < 19) return 'snack';
  return 'dinner';
}

/**
 * Places a real outbound call to the user's saved number.
 *
 * The number and consent live server-side; this never takes a phone number as
 * input. The button stays disabled until we have confirmed both, because a
 * button that rings a stranger's phone is the worst possible bug here.
 */
export default function CallMeButton() {
  const [slot, setSlot] = useState(slotNow());
  const [state, setState] = useState('idle');   // idle | calling | placed | error
  const [detail, setDetail] = useState(null);
  const [schedule, setSchedule] = useState(null);

  useEffect(() => {
    callSchedule().then(setSchedule).catch(() => setSchedule(null));
  }, []);

  const ready = schedule?.consent_to_call && schedule?.phone;

  const call = async () => {
    setState('calling');
    setDetail(null);
    try {
      const res = await placeCall({ slot });
      if (res.placed) {
        setState('placed');
        setDetail(`Ringing ${schedule.phone}`);
        setTimeout(() => setState('idle'), 8000);
      } else {
        setState('error');
        setDetail(res.reason || res.hint || `Sarvam returned ${res.status_code}`);
      }
    } catch (err) {
      setState('error');
      setDetail(err.response?.data?.detail || 'Could not place the call.');
    }
  };

  return (
    <div className="px-4 py-3 border-t border-white/[0.06]">
      <div className="text-[10px] uppercase tracking-[0.12em] text-gray-600 mb-2.5">
        Voice check-in
      </div>

      <div className="flex gap-1 mb-2">
        {SLOTS.map((s) => (
          <button
            key={s}
            onClick={() => setSlot(s)}
            className={`flex-1 text-[10px] py-1 rounded capitalize transition-colors ${
              slot === s
                ? 'bg-white/[0.09] text-gray-200'
                : 'text-gray-600 hover:text-gray-400'
            }`}
          >
            {s.slice(0, 5)}
          </button>
        ))}
      </div>

      <button
        onClick={call}
        disabled={!ready || state === 'calling'}
        title={ready ? `Call about ${slot}` : 'Add a number and consent in Household settings'}
        className={`w-full flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg text-[13px] border transition-colors ${
          state === 'placed'
            ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300'
            : state === 'error'
            ? 'border-red-500/30 bg-red-500/[0.07] text-red-300'
            : ready
            ? 'border-white/10 text-gray-300 hover:bg-white/[0.05] hover:border-white/20'
            : 'border-white/[0.06] text-gray-700 cursor-not-allowed'
        }`}
      >
        {state === 'calling' && <><Loader2 className="w-4 h-4 animate-spin" strokeWidth={1.75} /> Dialling…</>}
        {state === 'placed' && <><Check className="w-4 h-4" strokeWidth={2} /> Calling you now</>}
        {state === 'error' && <><AlertTriangle className="w-4 h-4" strokeWidth={1.75} /> Call failed</>}
        {state === 'idle' && (ready
          ? <><PhoneCall className="w-4 h-4" strokeWidth={1.75} /> Call me now</>
          : <><Phone className="w-4 h-4" strokeWidth={1.75} /> No number on file</>)}
      </button>

      {detail && (
        <p className={`mt-2 text-[11px] leading-relaxed ${
          state === 'error' ? 'text-red-400/80' : 'text-gray-600'
        }`}>
          {detail}
        </p>
      )}

      {ready && state === 'idle' && !detail && (
        <p className="mt-2 text-[11px] text-gray-700">
          {schedule.phone} · speaks Hindi
        </p>
      )}
    </div>
  );
}
