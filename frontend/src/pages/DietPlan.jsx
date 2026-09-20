import React, { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Flame, Activity, PieChart, RefreshCw, Loader2 } from 'lucide-react';
import { currentPlan } from '../services/api';

export default function DietPlan() {
  const location = useLocation();
  const navigate = useNavigate();
  const [activeDay, setActiveDay] = useState(1);

  // A plan handed over at navigation time wins; otherwise load the saved one,
  // so a refresh (or a plan generated in chat) still shows something.
  const [stored, setStored] = useState(null);
  const [loading, setLoading] = useState(!location.state?.plan);

  useEffect(() => {
    if (location.state?.plan) return;
    currentPlan()
      .then((d) => setStored(d.has_plan ? d.plan : null))
      .catch(() => setStored(null))
      .finally(() => setLoading(false));
  }, [location.state]);

  const plan = location.state?.plan || stored;

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2.5 py-32 text-gray-500">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading your plan
      </div>
    );
  }

  if (!plan) {
    return (
      <div className="text-center py-20">
        <h2 className="text-2xl font-bold mb-2">No Active Plan Found</h2>
        <p className="text-gray-400 mb-6 text-sm">
          Ask the assistant for a meal plan and it will be saved here.
        </p>
        <button 
          onClick={() => navigate('/')}
          className="bg-emerald-500 hover:bg-emerald-400 text-white px-6 py-2 rounded-lg"
        >
          Create Plan
        </button>
      </div>
    );
  }

  const currentDayPlan = plan.days.find(d => d.day === activeDay);

  return (
    <div className="space-y-8">
      {/* Top Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-white/5 border border-white/10 rounded-xl p-6 backdrop-blur-sm">
          <div className="flex items-center space-x-3 text-emerald-400 mb-2">
            <Flame className="w-5 h-5" />
            <h3 className="font-semibold">Daily Calories</h3>
          </div>
          <p className="text-3xl font-bold">{plan.daily_calorie_target} <span className="text-sm text-gray-400 font-normal">kcal</span></p>
        </div>
        <div className="bg-white/5 border border-white/10 rounded-xl p-6 backdrop-blur-sm">
          <div className="flex items-center space-x-3 text-blue-400 mb-2">
            <Activity className="w-5 h-5" />
            <h3 className="font-semibold">Protein</h3>
          </div>
          <p className="text-3xl font-bold">{plan.macro_targets.protein_g} <span className="text-sm text-gray-400 font-normal">g</span></p>
        </div>
        <div className="bg-white/5 border border-white/10 rounded-xl p-6 backdrop-blur-sm">
          <div className="flex items-center space-x-3 text-amber-400 mb-2">
            <PieChart className="w-5 h-5" />
            <h3 className="font-semibold">Carbs</h3>
          </div>
          <p className="text-3xl font-bold">{plan.macro_targets.carbs_g} <span className="text-sm text-gray-400 font-normal">g</span></p>
        </div>
        <div className="bg-white/5 border border-white/10 rounded-xl p-6 backdrop-blur-sm">
          <div className="flex items-center space-x-3 text-rose-400 mb-2">
            <Activity className="w-5 h-5" />
            <h3 className="font-semibold">Fat</h3>
          </div>
          <p className="text-3xl font-bold">{plan.macro_targets.fat_g} <span className="text-sm text-gray-400 font-normal">g</span></p>
        </div>
      </div>

      {/* Day Tabs */}
      <div className="flex space-x-2 overflow-x-auto pb-2 scrollbar-hide">
        {plan.days.map((d) => (
          <button
            key={d.day}
            onClick={() => setActiveDay(d.day)}
            className={`px-6 py-2 rounded-full whitespace-nowrap transition-colors ${
              activeDay === d.day
                ? 'bg-emerald-500 text-white font-medium shadow-lg'
                : 'bg-white/5 text-gray-400 hover:bg-white/10'
            }`}
          >
            Day {d.day}
          </button>
        ))}
      </div>

      {/* Meals List */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {currentDayPlan?.meals.map((meal, idx) => (
          <MealCard key={idx} meal={meal} />
        ))}
      </div>

      {/* Notes */}
      {plan.notes && plan.notes.length > 0 && (
        <div className="bg-blue-900/20 border border-blue-500/30 rounded-xl p-6 mt-8">
          <h3 className="text-lg font-semibold text-blue-300 mb-4">Doctor/AI Notes</h3>
          <ul className="list-disc list-inside space-y-2 text-blue-100/80">
            {plan.notes.map((note, i) => (
              <li key={i}>{note}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function MealCard({ meal }) {
  const [showSwap, setShowSwap] = useState(false);

  return (
    <div className="bg-white/5 border border-white/10 rounded-2xl p-6 backdrop-blur-sm hover:border-white/20 transition-colors flex flex-col">
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-xl font-bold capitalize text-emerald-400">{meal.slot}</h3>
        <span className="bg-black/50 px-3 py-1 rounded-full text-sm">{meal.total_calories} kcal</span>
      </div>

      <div className="flex-grow space-y-4">
        {/* Main Items */}
        <div className={`transition-opacity ${showSwap ? 'opacity-50 line-through' : 'opacity-100'}`}>
          <ul className="space-y-3">
            {meal.items.map((item, i) => (
              <li key={i} className="flex justify-between items-center text-sm">
                <span>{item.name}</span>
                <span className="text-gray-400">{item.portion_g}g</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Swap Alternative */}
        {showSwap && (
          <div className="bg-emerald-500/10 border border-emerald-500/30 rounded-lg p-4 mt-4 animate-in fade-in slide-in-from-top-2">
            <div className="text-xs font-semibold text-emerald-400 mb-2 uppercase tracking-wider">Alternative Swap</div>
            <ul className="space-y-2 mb-2">
              {meal.swap_alternative.items.map((item, i) => (
                <li key={i} className="flex justify-between text-sm">
                  <span>{item.name}</span>
                  <span className="text-gray-400">{item.portion_g}g</span>
                </li>
              ))}
            </ul>
            <p className="text-xs text-gray-400 italic">"{meal.swap_alternative.note}"</p>
          </div>
        )}
      </div>

      <button 
        onClick={() => setShowSwap(!showSwap)}
        className="mt-6 w-full flex items-center justify-center space-x-2 bg-white/5 hover:bg-white/10 text-gray-300 py-2 rounded-lg transition-colors"
      >
        <RefreshCw className="w-4 h-4" />
        <span>{showSwap ? 'Revert to Original' : 'Show Smart Swap'}</span>
      </button>
    </div>
  );
}
