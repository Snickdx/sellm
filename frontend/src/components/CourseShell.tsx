import { useState, type ReactNode } from 'react'
import { Link, NavLink } from 'react-router-dom'
import { useAuth } from '../auth'

type Props = {
  title: string
  subtitle?: string
  children: ReactNode
  aside?: ReactNode
}

export function CourseShell({ title, subtitle, children, aside }: Props) {
  const { user, logout } = useAuth()
  const [navOpen, setNavOpen] = useState(false)

  function closeNav() {
    setNavOpen(false)
  }

  return (
    <div className={`shell${navOpen ? ' nav-open' : ''}`}>
      <button
        type="button"
        className="nav-backdrop"
        aria-label="Close menu"
        onClick={closeNav}
      />
      <div className="master-detail">
        <aside className="nav-pane">
          <div className="nav-pane-header">
            <div>
              <p className="nav-kicker">SWEN · sellm</p>
              <h2>Exit interviews</h2>
            </div>
            <button type="button" className="nav-close" aria-label="Close menu" onClick={closeNav}>
              ×
            </button>
          </div>
          <nav className="nav-links" onClick={closeNav}>
            <NavLink to="/" end>
              Teams
            </NavLink>
            <NavLink to="/admin/teams">Create team</NavLink>
            <NavLink to="/policy">Policy</NavLink>
            <a href="/">← Requirements chat</a>
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
              <h1>{title}</h1>
              {subtitle ? <p>{subtitle}</p> : null}
            </div>
            <Link className="header-chat-link" to="/" onClick={closeNav}>
              Teams
            </Link>
          </header>
          <div className={`main-body${aside ? ' with-aside' : ''}`}>
            {aside ? <aside className="work-aside">{aside}</aside> : null}
            <div className="main-scroll">{children}</div>
          </div>
        </div>
      </div>
    </div>
  )
}
