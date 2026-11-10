import { useState, type ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { isInstructor } from '../api/client'
import { useAuth } from '../auth'

type Props = {
  title?: string
  subtitle?: string
  children: ReactNode
  aside?: ReactNode
  /** Extra child-tab row under Exit Interviews (e.g. team-specific). */
  tabs?: Array<{ to: string; label: string; end?: boolean }>
}

const EXIT_TABS = [
  { to: '/', label: 'Overview', end: true },
  { to: '/policy', label: 'Policy', end: true },
]

export function CourseShell({ title, subtitle, children, aside, tabs }: Props) {
  const { user, logout } = useAuth()
  const [navOpen, setNavOpen] = useState(false)
  const admin = isInstructor(user)
  const childTabs = tabs ?? EXIT_TABS

  function closeNav() {
    setNavOpen(false)
  }

  const heading = title ?? 'Exit interviews'

  return (
    <div className={`shell${navOpen ? ' nav-open' : ''}`}>
      <button type="button" className="nav-backdrop" aria-label="Close menu" onClick={closeNav} />
      <div className="master-detail">
        <aside className="nav-pane">
          <div className="nav-pane-header">
            <div>
              <p className="nav-kicker">SWEN · sellm</p>
              <h2>Course</h2>
            </div>
            <button type="button" className="nav-close" aria-label="Close menu" onClick={closeNav}>
              ×
            </button>
          </div>

          <nav className="app-nav" aria-label="Primary" onClick={closeNav}>
            <a href="/">Chats</a>
            <span className="active" aria-current="page">
              Exit interviews
            </span>
            {admin ? <a href="/admin">Admin</a> : null}
          </nav>

          <div className="nav-section-label">Exit interviews</div>
          <nav className="nav-links child-tabs" onClick={closeNav}>
            {childTabs.map((t) => (
              <NavLink key={t.to} to={t.to} end={t.end}>
                {t.label}
              </NavLink>
            ))}
          </nav>

          <div className="nav-footer">
            <span className="nav-user">
              {user?.display_name ?? '…'} · {user?.role ?? ''}
            </span>
            <button type="button" className="ghost" onClick={logout}>
              Log out
            </button>
          </div>
        </aside>

        <div className="main-pane">
          <header className="main-header">
            <button
              type="button"
              className="nav-toggle"
              aria-label="Open menu"
              aria-expanded={navOpen}
              onClick={() => setNavOpen(true)}
            >
              ☰
            </button>
            <div className="main-header-text">
              <h1>{heading}</h1>
              {subtitle ? <p>{subtitle}</p> : null}
            </div>
          </header>

          <div className="child-tab-bar" role="tablist" aria-label="Exit interview sections">
            {childTabs.map((t) => (
              <NavLink key={t.to} to={t.to} end={t.end} role="tab">
                {t.label}
              </NavLink>
            ))}
          </div>

          <div className={`main-body${aside ? ' with-aside' : ''}`}>
            {aside ? <aside className="work-aside">{aside}</aside> : null}
            <div className="main-scroll">{children}</div>
          </div>
        </div>
      </div>
    </div>
  )
}
