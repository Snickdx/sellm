import { Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './auth'
import { HomePage } from './pages/HomePage'
import { LoginPage } from './pages/LoginPage'
import { AdminReposPage } from './pages/AdminReposPage'
import { ExitInterviewPage } from './pages/ExitInterviewPage'
import { PolicyPage } from './pages/PolicyPage'

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/policy" element={<PolicyPage />} />
        <Route path="/teams/:teamId/exit" element={<ExitInterviewPage />} />
        <Route path="/admin/teams/:teamId/repository" element={<AdminReposPage />} />
        <Route path="/admin/teams" element={<Navigate to="/" replace />} />
        <Route path="/teams/:teamId/interviews" element={<Navigate to="/" replace />} />
        <Route path="/admin/scenarios" element={<Navigate to="/" replace />} />
        <Route path="/admin/teams/:teamId/transcripts" element={<Navigate to="/" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  )
}
