import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
});

export const healthCheck = async () => {
  const response = await api.get('/health');
  return response.data;
};

export const generateDietPlan = async (payload) => {
  const response = await api.post('/diet-plan/generate', payload);
  return response.data;
};

export const generateRecommendations = async (payload) => {
  const response = await api.post('/recommendations/generate', payload);
  return response.data;
};

export const analyzeMealPhoto = async (file, opts = {}) => {
  const form = new FormData();
  form.append('file', file);
  form.append('user_id', String(opts.user_id ?? 1));
  form.append('hint', opts.hint ?? '');
  form.append('cooking_method', opts.cooking_method ?? 'home');
  form.append('oil_level', opts.oil_level ?? 'normal');
  const response = await api.post('/food-vision/analyze', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return response.data;
};

export const householdSplit = async (payload) => {
  const response = await api.post('/insights/household', payload);
  return response.data;
};

export const micronutrients = async (payload) => {
  const response = await api.post('/insights/micronutrients', payload);
  return response.data;
};

export const optimizeCost = async (payload) => {
  const response = await api.post('/insights/optimize-cost', payload);
  return response.data;
};

export const fitnessTargets = async (payload) => {
  const response = await api.post('/insights/fitness', payload);
  return response.data;
};

export const safetyScreen = async (payload) => {
  const response = await api.post('/insights/safety', payload);
  return response.data;
};

export const chatAgents = async () => (await api.get('/chat/agents')).data;

export const listSessions = async (userId = 1) =>
  (await api.get('/chat/sessions', { params: { user_id: userId } })).data;

export const createSession = async (payload) =>
  (await api.post('/chat/sessions', payload)).data;

export const getSession = async (id) =>
  (await api.get(`/chat/sessions/${id}`)).data;

export const deleteSession = async (id) =>
  (await api.delete(`/chat/sessions/${id}`)).data;

export const sendMessage = async (id, payload) =>
  (await api.post(`/chat/sessions/${id}/message`, payload)).data;

export const gamificationStatus = async (userId = 'default') =>
  (await api.get(`/gamification/status/${userId}`)).data;

export const habitCheckIn = async (payload) =>
  (await api.post('/gamification/check-in', payload)).data;

export const gamificationConfig = async () =>
  (await api.get('/gamification/config')).data;

export const logCalendar = async (userId = 1) =>
  (await api.get('/chat/calendar', { params: { user_id: userId } })).data;

export const logCalendarDay = async (day, userId = 1) =>
  (await api.get(`/chat/calendar/${day}`, { params: { user_id: userId } })).data;

export const placeCall = async (payload = {}) =>
  (await api.post('/agent/sarvam/call', { user_id: 1, language: 'hi-IN', ...payload })).data;

export const callSchedule = async (userId = 1) =>
  (await api.get('/agent/schedule', { params: { user_id: userId } })).data;

export const currentPlan = async (userId = 1) =>
  (await api.get('/diet-plan/current', { params: { user_id: userId } })).data;

export default api;
