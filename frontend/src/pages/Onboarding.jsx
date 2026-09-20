import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { generateDietPlan } from '../services/api';

export default function Onboarding() {
  const navigate = useNavigate();
  const [formData, setFormData] = useState({
    age: 25,
    gender: 'female',
    height_cm: 165,
    weight_kg: 65,
    activity_level: 'moderate',
    medical_conditions: '',
    goal_type: 'weight_loss',
    target_calories: '',
    diet_type: 'veg',
    cuisine_preference: 'indian',
    allergies: '',
    dislikes: ''
  });
  
  const [errorMsg, setErrorMsg] = useState(null);

  const mutation = useMutation({
    mutationFn: generateDietPlan,
    onSuccess: (data) => {
      // For demo purposes, we pass the data via state to the next route
      // Real apps would use a global store or context
      navigate('/plan', { state: { plan: data } });
    },
    onError: (error) => {
      setErrorMsg(error.response?.data?.detail || "Failed to generate plan. Check your API Key.");
    }
  });

  const handleChange = (e) => {
    setFormData({...formData, [e.target.name]: e.target.value});
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    const payload = {
      profile: {
        age: Number(formData.age),
        gender: formData.gender,
        height_cm: Number(formData.height_cm),
        weight_kg: Number(formData.weight_kg),
        activity_level: formData.activity_level,
        medical_conditions: formData.medical_conditions ? formData.medical_conditions.split(',').map(s => s.trim()) : []
      },
      goals: {
        goal_type: formData.goal_type,
        target_calories: formData.target_calories ? Number(formData.target_calories) : null
      },
      preferences: {
        diet_type: formData.diet_type,
        cuisine_preference: formData.cuisine_preference,
        allergies: formData.allergies ? formData.allergies.split(',').map(s => s.trim()) : [],
        dislikes: formData.dislikes ? formData.dislikes.split(',').map(s => s.trim()) : []
      },
      plan_length_days: 7
    };
    mutation.mutate(payload);
  };

  return (
    <div className="max-w-2xl mx-auto">
      <div className="bg-white/5 border border-white/10 rounded-2xl p-8 backdrop-blur-sm shadow-xl">
        <h1 className="text-3xl font-bold mb-2">Build Your Profile</h1>
        <p className="text-gray-400 mb-8">Tell us about yourself to get a personalized meal plan.</p>
        
        {errorMsg && (
            <div className="bg-red-500/20 border border-red-500/50 text-red-200 p-4 rounded-lg mb-6">
                {errorMsg}
            </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="grid grid-cols-2 gap-6">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Age</label>
              <input type="number" name="age" value={formData.age} onChange={handleChange} className="w-full bg-black/40 border border-white/10 rounded-lg px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-emerald-500" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Gender</label>
              <select name="gender" value={formData.gender} onChange={handleChange} className="w-full bg-black/40 border border-white/10 rounded-lg px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-emerald-500">
                <option value="male">Male</option>
                <option value="female">Female</option>
                <option value="other">Other</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Height (cm)</label>
              <input type="number" name="height_cm" value={formData.height_cm} onChange={handleChange} className="w-full bg-black/40 border border-white/10 rounded-lg px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-emerald-500" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Weight (kg)</label>
              <input type="number" name="weight_kg" value={formData.weight_kg} onChange={handleChange} className="w-full bg-black/40 border border-white/10 rounded-lg px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-emerald-500" />
            </div>
          </div>

          <div className="border-t border-white/10 pt-6">
            <h2 className="text-xl font-semibold mb-4">Goals & Activity</h2>
            <div className="grid grid-cols-2 gap-6">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Activity Level</label>
                <select name="activity_level" value={formData.activity_level} onChange={handleChange} className="w-full bg-black/40 border border-white/10 rounded-lg px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-emerald-500">
                  <option value="sedentary">Sedentary</option>
                  <option value="light">Lightly Active</option>
                  <option value="moderate">Moderately Active</option>
                  <option value="very">Very Active</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Goal Type</label>
                <select name="goal_type" value={formData.goal_type} onChange={handleChange} className="w-full bg-black/40 border border-white/10 rounded-lg px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-emerald-500">
                  <option value="weight_loss">Weight Loss</option>
                  <option value="maintenance">Maintenance</option>
                  <option value="weight_gain">Weight Gain</option>
                  <option value="muscle_gain">Muscle Gain</option>
                </select>
              </div>
            </div>
          </div>

          <div className="border-t border-white/10 pt-6">
            <h2 className="text-xl font-semibold mb-4">Dietary Preferences</h2>
            <div className="grid grid-cols-2 gap-6">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Diet Type</label>
                <select name="diet_type" value={formData.diet_type} onChange={handleChange} className="w-full bg-black/40 border border-white/10 rounded-lg px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-emerald-500">
                  <option value="veg">Vegetarian</option>
                  <option value="non_veg">Non-Vegetarian</option>
                  <option value="vegan">Vegan</option>
                  <option value="eggetarian">Eggetarian</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Allergies (comma-separated)</label>
                <input type="text" name="allergies" placeholder="e.g. peanuts, dairy" value={formData.allergies} onChange={handleChange} className="w-full bg-black/40 border border-white/10 rounded-lg px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-emerald-500" />
              </div>
            </div>
          </div>

          <div className="pt-4">
            <button 
              type="submit" 
              disabled={mutation.isPending}
              className="w-full bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 text-white font-bold py-3 px-4 rounded-lg shadow-lg transform transition active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {mutation.isPending ? "Analyzing & Generating Plan..." : "Generate AI Meal Plan"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
