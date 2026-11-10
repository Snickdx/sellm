import { useState, type ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { isInstructor } from '../api/client'
import { useAuth } from '../auth'

export type CourseTab = {
  id: string
  label: string
  /** When true, tab is shown but not clickable (status indicator only). */
  disabled?: boolean
}

type Props = {
  title?: string
  subtitle?: string
  children: ReactNode
  aside?: ReactNode
  tabs?: CourseTab[]
  activeTab?: string
  onTabChange?: (id: string) => void
}

export function CourseShell({
  title,
  subtitle,
  children,
  aside,
  tabs,
  activeTab,
  onTabChange,
}: Props) {
  const { user, logout } = useAuth()
  const [navOpen, setNavOpen] = useState(false)
  const admin = isInstructor(user)

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
            <a href="/req">Req Interviews</a>
            <span className="active" aria-current="page">
              Exit interviews
            </span>
            {admin ? <a href="/admin">Admin</a> : null}
          </nav>

          <div className="nav-footer">
            <NavLink to="/policy" className="nav-policy" onClick={closeNav}>
              Consent &amp; policy
            </NavLink>
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

          {tabs && tabs.length > 0 ? (
            <div className="child-tab-bar" role="tablist" aria-label="Exit sections">
              {tabs.map((tab) => {
                const on = tab.id === activeTab
                return (
                  <button
                    key={tab.id}
                    type="button"
                    role="tab"
                    aria-selected={on}
                    disabled={tab.disabled}
                    className={on ? 'active' : undefined}
                    onClick={() => {
                      if (tab.disabled) return
                      onTabChange?.(tab.id)
                    }}
                  >
                    {tab.label}
                  </button>
                )
              })}
            </div>
          ) : null}

          <div className={`main-body${aside ? ' with-aside' : ''}`}>
            {aside ? <aside className="work-aside">{aside}</aside> : null}
            <div className="main-scroll">{children}</div>
          </div>
        </div>
      </div>
    </div>
  )
}
