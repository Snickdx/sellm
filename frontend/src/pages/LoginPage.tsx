import { Navigate } from 'react-router-dom'
import { useAuth } from '../auth'
import { LandingPage } from './LandingPage'

/** Login lives on the landing page with group claim. */
export function LoginPage() {
  const { user, loading } = useAuth()
  if (!loading && user) return <Navigate to="/" replace />
  return <LandingPage />
}
