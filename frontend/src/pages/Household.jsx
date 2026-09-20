import React, { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Users, Camera, IndianRupee, AlertTriangle, ShieldCheck, Activity } from 'lucide-react';
import { analyzeMealPhoto, householdSplit, optimizeCost } from '../services/api';

const DEMO_MEAL = [
  { name: 'Wheat flour, atta', portion_g: 400 },
  { name: 'Bengal gram, dal', portion_g: 250 },
  { name: 'Spinach', portion_g: 300 },
  { name: 'Rice, raw, milled', portion_g: 200 },
];

const DEMO_FAMILY = [
  { name: 'Dad', age: 48, gender: 'male', weight_kg: 78, height_cm: 172,
    medical_conditions: ['diabetes'], medications: ['metformin'] },
  { name: 'Mom', age: 42, gender: 'female', weight_kg: 62, height_cm: 158,
    medical_conditions: [], medications: [] },
  { name: 'Priya', age: 14, gender: 'female', weight_kg: 45, height_cm: 152,
    medical_conditions: [], medications: [] },
  { name: 'Arjun', age: 8, gender: 'male', weight_kg: 25, height_cm: 128,
    medical_conditions: [], medications: [] },
];

const TIMING_LABELS = {
  with_meal: 'Chai with the meal',
  within_hour: 'Chai within an hour',
  separated: 'Chai 90 min after',
};

export default function Household() {
  const [items, setItems] = useState(DEMO_MEAL);
  const [timing, setTiming] = useState('with_meal');
  const [photoName, setPhotoName] = useState(null);
  const [result, setResult] = useState(null);
  const [basket, setBasket] = useState(null);
  const [error, setError] = useState(null);

  const split = useMutation({
    mutationFn: () => householdSplit({ items, members: DEMO_FAMILY, tea_coffee_timing: timing }),
    onSuccess: setResult,
    onError: (e) => setError(e.response?.data?.detail || 'Split failed.'),
  });

  const photo = useMutation({
    mutationFn: (file) => analyzeMealPhoto(file, { cooking_method: 'home', oil_level: 'normal' }),
    onSuccess: (data) => {
      const detected = (data.items || []).map((i) => ({
        name: i.name, portion_g: Math.round(i.portion_g),
      }));
      if (detected.length) setItems(detected);
      setError(null);
    },
    onError: (e) => setError(e.response?.data?.detail || 'Photo analysis failed.'),
  });

  const cost = useMutation({
    mutationFn: (gaps) => optimizeCost({ gaps, budget: 200, diet_type: 'veg' }),
    onSuccess: setBasket,
    onError: (e) => setError(e.response?.data?.detail || 'Optimiser failed.'),
  });

  const onPhoto = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setPhotoName(file.name);
    photo.mutate(file);
  };

  const closeGapFor = (member) => {
    const gaps = {};
    (member.top_gaps || []).forEach((g) => {
      const deficit = Math.max(g.rda - g.intake, 0);
      if (deficit > 0 && ['iron_mg', 'calcium_mg', 'zinc_mg', 'protein_g',
        'folate_ug', 'vitamin_a_ug', 'vitamin_c_mg'].includes(g.key)) {
        gaps[g.key] = Number(deficit.toFixed(2));
      }
    });
    if (Object.keys(gaps).length) cost.mutate(gaps);
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold mb-2 flex items-center gap-3">
          <Users className="w-7 h-7 text-emerald-400" /> Household Mode
        </h1>
        <p className="text-gray-400">
          One pot, four people, four different requirements. Nutrients come from
          IFCT 2017 (ICMR); iron is judged on what is absorbed, not what is served.
        </p>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 text-red-300 p-4 rounded-xl">
          {error}
        </div>
      )}

      {/* Meal input */}
      <div className="bg-white/5 border border-white/10 rounded-2xl p-6 space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <h2 className="text-lg font-semibold">What is in the pot</h2>
          <label className="cursor-pointer flex items-center gap-2 bg-white/5 hover:bg-white/10 border border-white/10 px-4 py-2 rounded-lg text-sm transition-colors">
            <Camera className="w-4 h-4" />
            {photo.isPending ? 'Reading photo…' : 'Photograph the thali'}
            <input type="file" accept="image/*" className="hidden" onChange={onPhoto} />
          </label>
        </div>

        {photoName && (
          <p className="text-xs text-gray-500">
            From <span className="text-gray-300">{photoName}</span> — check the grams,
            portion estimates from a photo are the least reliable part.
          </p>
        )}

        <div className="grid sm:grid-cols-2 gap-3">
          {items.map((it, idx) => (
            <div key={idx} className="flex items-center gap-3 bg-black/30 border border-white/10 rounded-lg px-3 py-2">
              <span className="flex-1 text-sm truncate">{it.name}</span>
              <input
                type="number"
                value={it.portion_g}
                onChange={(e) => {
                  const next = [...items];
                  next[idx] = { ...it, portion_g: Number(e.target.value) };
                  setItems(next);
                }}
                className="w-20 bg-black/40 border border-white/10 rounded px-2 py-1 text-sm text-right"
              />
              <span className="text-xs text-gray-500">g</span>
            </div>
          ))}
        </div>

        {/* The demo moment */}
        <div>
          <label className="block text-sm text-gray-400 mb-2">
            When is the chai or coffee?
          </label>
          <div className="flex flex-wrap gap-2">
            {Object.entries(TIMING_LABELS).map(([value, label]) => (
              <button
                key={value}
                onClick={() => setTiming(value)}
                className={`px-4 py-2 rounded-lg text-sm border transition-colors ${
                  timing === value
                    ? 'bg-emerald-500 border-emerald-400 text-white font-medium'
                    : 'bg-white/5 border-white/10 text-gray-400 hover:bg-white/10'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <button
          onClick={() => { setError(null); split.mutate(); }}
          disabled={split.isPending}
          className="w-full bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 text-white font-medium py-3 rounded-lg transition-colors"
        >
          {split.isPending ? 'Splitting…' : 'Split across the family'}
        </button>
      </div>

      {/* Per-person results */}
      {result && (
        <>
          <div className="grid gap-5 md:grid-cols-2">
            {result.members.map((m) => (
              <MemberCard key={m.name} member={m} onCloseGap={() => closeGapFor(m)} />
            ))}
          </div>

          <div className="bg-white/5 border border-white/10 rounded-2xl p-6">
            <h3 className="font-semibold mb-1">One cooking session</h3>
            <p className="text-sm text-gray-400 mb-4">{result.cooking_plan.shared_base}</p>
            <ul className="space-y-2">
              {result.cooking_plan.per_person_tweaks.slice(0, 6).map((t, i) => (
                <li key={i} className="text-sm flex gap-3">
                  <span className="text-emerald-400 font-medium min-w-[3.5rem]">{t.member}</span>
                  <span className="text-gray-300">
                    {t.tweak}
                    <span className="text-gray-500"> — {t.because}</span>
                  </span>
                </li>
              ))}
            </ul>
            <p className="text-xs text-gray-500 mt-4">{result.caveat}</p>
          </div>
        </>
      )}

      {/* Cost basket */}
      {basket && basket.basket?.length > 0 && (
        <div className="bg-amber-500/5 border border-amber-500/25 rounded-2xl p-6">
          <h3 className="font-semibold mb-3 flex items-center gap-2 text-amber-300">
            <IndianRupee className="w-5 h-5" /> Cheapest way to close that gap
          </h3>
          <div className="space-y-2 mb-4">
            {basket.basket.map((b, i) => (
              <div key={i} className="flex justify-between text-sm">
                <span>{b.food}</span>
                <span className="text-gray-400">{b.grams} g · ₹{b.cost.toFixed(2)}</span>
              </div>
            ))}
          </div>
          <div className="flex justify-between font-semibold border-t border-white/10 pt-3">
            <span>Total</span>
            <span className="text-amber-300">₹{basket.total_cost.toFixed(2)}</span>
          </div>
          <p className="text-xs text-gray-500 mt-3">
            Solved with {basket.solver}. {basket.prices?.warning}
          </p>
        </div>
      )}
    </div>
  );
}

function MemberCard({ member, onCloseGap }) {
  const ab = member.iron_absorption || {};
  const pq = member.protein_quality || {};
  const blocking = (member.safety?.findings || []).filter((f) => f.severity === 'block');
  const warnings = (member.safety?.findings || []).filter((f) => f.severity !== 'block');

  return (
    <div className="bg-white/5 border border-white/10 rounded-2xl p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-bold">{member.name}</h3>
        <span className="text-xs text-gray-500 bg-black/40 px-2 py-1 rounded-full">
          {member.profile.replace(/_/g, ' ')} · {(member.share * 100).toFixed(0)}% of pot
        </span>
      </div>

      <div className="grid grid-cols-3 gap-2 text-center">
        <Stat label="kcal" value={Math.round(member.totals.calories)} />
        <Stat label="protein" value={`${Math.round(member.totals.protein_g)}g`} />
        <Stat label="fibre" value={`${Math.round(member.totals.fiber_g)}g`} />
      </div>

      {/* The absorption story */}
      <div className="bg-black/30 rounded-lg p-4 border border-white/5">
        <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-gray-500 mb-2">
          <Activity className="w-3.5 h-3.5" /> Iron
        </div>
        <div className="flex items-baseline gap-2">
          <span className="text-gray-500 line-through text-sm">{ab.iron_intake_mg} mg served</span>
          <span className="text-2xl font-bold text-emerald-400">{ab.iron_absorbed_mg} mg</span>
          <span className="text-xs text-gray-500">absorbed</span>
        </div>
        {ab.recoverable_mg > 0 && (
          <p className="text-xs text-amber-300 mt-2">
            +{ab.recoverable_mg} mg recoverable by moving the chai
          </p>
        )}
      </div>

      {pq.triggers_mps === false && pq.close_the_gap_with?.length > 0 && (
        <p className="text-xs text-blue-300 bg-blue-500/10 border border-blue-500/20 rounded-lg p-3">
          {pq.protein_g} g protein but only {pq.leucine_g} g leucine — below the
          muscle-synthesis threshold. Add {pq.close_the_gap_with[0]}.
        </p>
      )}

      {blocking.map((f, i) => (
        <p key={i} className="text-xs text-red-300 bg-red-500/10 border border-red-500/25 rounded-lg p-3 flex gap-2">
          <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <span><strong>Needs a dietitian.</strong> {f.action}</span>
        </p>
      ))}

      {warnings.map((f, i) => (
        <p key={i} className="text-xs text-amber-200/90 bg-amber-500/10 border border-amber-500/20 rounded-lg p-3 flex gap-2">
          <ShieldCheck className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <span>{f.message} <em className="text-gray-400">{f.citation}</em></span>
        </p>
      ))}

      {member.top_gaps?.length > 0 && (
        <div>
          <div className="space-y-1.5 mb-3">
            {member.top_gaps.map((g, i) => (
              <div key={i} className="flex justify-between text-xs">
                <span className="text-gray-400">{g.nutrient}</span>
                <span className={g.status === 'deficient' ? 'text-rose-400' : 'text-amber-400'}>
                  {g.percent_rda}% of RDA
                </span>
              </div>
            ))}
          </div>
          <button
            onClick={onCloseGap}
            className="w-full text-xs bg-white/5 hover:bg-white/10 border border-white/10 py-2 rounded-lg transition-colors"
          >
            Close this gap for the least money
          </button>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div className="bg-black/30 rounded-lg py-2">
      <div className="text-lg font-semibold">{value}</div>
      <div className="text-[10px] uppercase tracking-wider text-gray-500">{label}</div>
    </div>
  );
}
