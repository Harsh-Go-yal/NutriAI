import React from 'react'
import { BrowserRouter, Routes, Route, Link, useLocation } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import Onboarding from './pages/Onboarding'
import DietPlan from './pages/DietPlan'
import Recommendations from './pages/Recommendations'
import Household from './pages/Household'
import Chat from './pages/Chat'
import { Activity } from 'lucide-react'

const queryClient = new QueryClient()

function Shell() {
  const { pathname } = useLocation();
  const wide = pathname.startsWith('/chat');
  return (
    <div className="min-h-screen bg-[#121212] text-white font-sans">
          <nav className="border-b border-white/10 bg-black/50 backdrop-blur-md sticky top-0 z-50">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
              <div className="flex items-center justify-between h-16">
                <div className="flex items-center space-x-3">
                  <Activity className="w-8 h-8 text-emerald-400" />
                  <span className="font-bold text-xl tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-emerald-400 to-teal-200">
                    NutriAI Assistant
                  </span>
                </div>
                <div className="flex space-x-6 text-sm font-medium">
                  <Link to="/chat" className="text-emerald-300 hover:text-white transition-colors">Chat</Link>
                  <Link to="/" className="text-gray-300 hover:text-white transition-colors">Onboarding</Link>
                  <Link to="/plan" className="text-gray-300 hover:text-white transition-colors">My Plan</Link>
                  <Link to="/recommendations" className="text-gray-300 hover:text-white transition-colors">Insights</Link>
                  <Link to="/household" className="text-emerald-300 hover:text-white transition-colors">Household</Link>
                </div>
              </div>
            </div>
          </nav>

          <main className={wide ? "px-3 pb-3" : "max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8"}>
            <Routes>
              <Route path="/" element={<Onboarding />} />
              <Route path="/plan" element={<DietPlan />} />
              <Route path="/recommendations" element={<Recommendations />} />
              <Route path="/household" element={<Household />} />
              <Route path="/chat" element={<Chat />} />
            </Routes>
      </main>
    </div>
  )
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Shell />
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App
