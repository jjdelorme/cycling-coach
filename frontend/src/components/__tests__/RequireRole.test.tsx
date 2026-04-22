import { describe, it, expect, vi } from 'vitest'
import { renderToString } from 'react-dom/server'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import RequireRole from '../RequireRole'

// Stub useAuth so RequireRole's role check is fully under our control.
let mockAuth: { user: { role: string } | null; isLoading: boolean } = {
  user: null,
  isLoading: false,
}
vi.mock('../../lib/auth', () => ({
  useAuth: () => mockAuth,
}))

function renderAt(url: string, role: 'admin' | 'readwrite' | 'read', child: React.ReactNode) {
  return renderToString(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path="/" element={<div id="home">HOME</div>} />
        <Route path="/admin" element={<RequireRole role={role}>{child}</RequireRole>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('RequireRole', () => {
  it('renders the loading screen while auth is initializing', () => {
    mockAuth = { user: null, isLoading: true }
    const html = renderAt('/admin', 'admin', <div id="protected">SECRET</div>)
    expect(html).toContain('Loading...')
    expect(html).not.toContain('SECRET')
  })

  // Note: MemoryRouter + SSR does not follow <Navigate> to render the target —
  // it short-circuits the matched route to empty. Asserting "SECRET is hidden"
  // is therefore the proof that the redirect fired.
  it('redirects to "/" when the user lacks the required role', () => {
    mockAuth = { user: { role: 'read' }, isLoading: false }
    const html = renderAt('/admin', 'admin', <div id="protected">SECRET</div>)
    expect(html).not.toContain('SECRET')
    expect(html).not.toContain('Loading...')
  })

  it('redirects when the user is unauthenticated (no user object)', () => {
    mockAuth = { user: null, isLoading: false }
    const html = renderAt('/admin', 'admin', <div id="protected">SECRET</div>)
    expect(html).not.toContain('SECRET')
    expect(html).not.toContain('Loading...')
  })

  it('renders children when the role satisfies the requirement', () => {
    mockAuth = { user: { role: 'admin' }, isLoading: false }
    const html = renderAt('/admin', 'admin', <div id="protected">SECRET</div>)
    expect(html).toContain('SECRET')
  })

  it('honours the role hierarchy (admin satisfies read)', () => {
    mockAuth = { user: { role: 'admin' }, isLoading: false }
    const html = renderAt('/admin', 'read', <div id="protected">SECRET</div>)
    expect(html).toContain('SECRET')
  })
})
