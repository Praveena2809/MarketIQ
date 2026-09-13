import { useState } from 'react'
import { Routes, Route } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import Header from './components/Header'
import DashboardPage from './pages/DashboardPage'
import NewResearchPage from './pages/NewResearchPage'
import ResearchReportPage from './pages/ResearchReportPage'
import ReportsPage from './pages/ReportsPage'
import CompetitorsPage from './pages/CompetitorsPage'
import TrendsPage from './pages/TrendsPage'
import SentimentPage from './pages/SentimentPage'
import SourcesPage from './pages/SourcesPage'
import PlaceholderPage from './pages/PlaceholderPage'

export default function App() {
  const [sidebarOpen, setSidebarOpen] = useState(false)

  return (
    <div className="flex min-h-screen bg-paper">
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <main className="flex min-w-0 flex-1 flex-col">
        <Header onMenuClick={() => setSidebarOpen(true)} />
        <div className="flex-1 overflow-y-auto">
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/research/new" element={<NewResearchPage />} />
            <Route path="/research/:id" element={<ResearchReportPage />} />
            <Route path="/reports" element={<ReportsPage />} />
            <Route path="/competitors" element={<CompetitorsPage />} />
            <Route path="/trends" element={<TrendsPage />} />
            <Route path="/sentiment" element={<SentimentPage />} />
            <Route path="/sources" element={<SourcesPage />} />
            <Route
              path="/settings"
              element={<PlaceholderPage title="Settings" description="Account and API configuration settings will live here." />}
            />
          </Routes>
        </div>
      </main>
    </div>
  )
}