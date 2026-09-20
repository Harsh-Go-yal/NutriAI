import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { generateRecommendations } from '../services/api';
import { AlertTriangle, Lightbulb, Activity, CheckCircle2 } from 'lucide-react';

export default function Recommendations() {
  const [loggedMeals, setLoggedMeals] = useState([
    { name: "Oats", portion_g: 100, calories: 389 } // Mock data for demo
  ]);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['recommendations'],
    queryFn: () => generateRecommendations({
      user_id: 1, // Demo user
      logged_today: loggedMeals,
      recent_activity: { steps: 5000, water_intake_ml: 1000 },
      adherence_history: { hit_target: false, missed_meals: 1 }
    }),
    retry: false
  });

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-32 space-y-4">
        <div className="w-8 h-8 border-4 border-emerald-500 border-t-transparent rounded-full animate-spin"></div>
        <p className="text-gray-400">Analyzing your adherence and activity...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-500/10 border border-red-500/30 text-red-400 p-6 rounded-xl max-w-2xl mx-auto mt-8 text-center">
        <p>{error.response?.data?.detail || "Failed to fetch recommendations. Ensure you have generated a diet plan first."}</p>
        <button onClick={() => refetch()} className="mt-4 px-4 py-2 bg-red-500/20 hover:bg-red-500/30 rounded-lg transition-colors">Retry</button>
      </div>
    );
  }

  const getPriorityColor = (priority) => {
    switch(priority) {
      case 'high': return 'text-rose-400 bg-rose-400/10 border-rose-400/20';
      case 'medium': return 'text-amber-400 bg-amber-400/10 border-amber-400/20';
      default: return 'text-blue-400 bg-blue-400/10 border-blue-400/20';
    }
  };

  const getIcon = (type) => {
    switch(type) {
      case 'alert': return <AlertTriangle className="w-5 h-5" />;
      case 'swap': return <Lightbulb className="w-5 h-5" />;
      case 'adjustment': return <Activity className="w-5 h-5" />;
      default: return <CheckCircle2 className="w-5 h-5" />;
    }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold mb-2">Real-time Insights</h1>
          <p className="text-gray-400">Smart adjustments based on your logged day.</p>
        </div>
        <button 
          onClick={() => refetch()}
          className="bg-white/5 hover:bg-white/10 px-4 py-2 rounded-lg transition-colors border border-white/10"
        >
          Refresh Data
        </button>
      </div>

      {data?.summary && (
        <div className="bg-emerald-500/10 border border-emerald-500/30 p-6 rounded-xl text-emerald-100/90 text-lg">
          {data.summary}
        </div>
      )}

      <div className="space-y-4">
        {data?.recommendations?.map((rec, idx) => (
          <div key={idx} className={`p-6 rounded-xl border flex gap-4 ${getPriorityColor(rec.priority)} backdrop-blur-sm transition-transform hover:-translate-y-1`}>
            <div className="flex-shrink-0 mt-1">
              {getIcon(rec.type)}
            </div>
            <div>
              <div className="flex items-center gap-3 mb-2">
                <span className="uppercase text-xs font-bold tracking-wider">{rec.type}</span>
                <span className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded-full ${rec.priority === 'high' ? 'bg-rose-500/20' : 'bg-white/10'}`}>
                  {rec.priority} priority
                </span>
              </div>
              <p className="font-medium mb-1 text-white">{rec.message}</p>
              <p className="text-sm opacity-80">{rec.reason}</p>
            </div>
          </div>
        ))}
        {(!data?.recommendations || data.recommendations.length === 0) && (
          <div className="text-center py-12 text-gray-400 bg-white/5 rounded-xl border border-white/10">
            No recommendations at this time. You're doing great!
          </div>
        )}
      </div>
    </div>
  );
}
