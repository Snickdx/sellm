import { Navigate } from 'react-router-dom'
import { useAuth } from '../auth'
import { LandingPage } from './LandingPage'

/** Claim UX is the landing page alongside login. */
export function ClaimGroupPage() {
  const { user, loading } = useAuth()
  if (!loading && user) return <Navigate to="/" replace />
  return <LandingPage />
}
