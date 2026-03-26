import { useEffect, useRef } from 'react'
import { useAuth } from '../lib/auth'

export default function LoginPage() {
  const { user, isAuthenticated, login } = useAuth()
  const buttonRef = useRef<HTMLDivElement>(null)

  // Render Google's sign-in button when GSI is ready
  useEffect(() => {
    if (!buttonRef.current) return
    const interval = setInterval(() => {
      if (window.google?.accounts?.id && buttonRef.current) {
        clearInterval(interval)
        window.google.accounts.id.renderButton(buttonRef.current, {
          theme: 'outline',
          size: 'large',
          text: 'signin_with',
          shape: 'rectangular',
        })
      }
    }, 100)
    const timeout = setTimeout(() => clearInterval(interval), 5000)
    return () => { clearInterval(interval); clearTimeout(timeout) }
  }, [])

  // Authenticated but no access (role === 'none')
  if (isAuthenticated && user?.role === 'none') {
    return (
      <div className="flex items-center justify-center h-screen bg-bg">
        <div className="text-center max-w-md p-8">
          <div className="text-6xl mb-4">🚴</div>
          <h1 className="text-2xl font-bold text-text mb-2">Waiting for Access</h1>
          <p className="text-text-muted mb-2">
            Signed in as <span className="text-text font-medium">{user.email}</span>
          </p>
          <p className="text-text-muted mb-6">
            An administrator needs to grant you access before you can use this app.
          </p>
          <button
            onClick={() => window.location.reload()}
            className="px-4 py-2 bg-surface2 text-text border border-border rounded text-sm font-medium hover:opacity-90"
          >
            Check Again
          </button>
        </div>
      </div>
    )
  }

  // Not authenticated — show login
  return (
    <div className="flex items-center justify-center h-screen bg-bg">
      <div className="text-center max-w-md p-8">
        <div className="text-6xl mb-4">🚴</div>
        <h1 className="text-2xl font-bold text-text mb-2">Cycling Coach</h1>
        <p className="text-text-muted mb-8">
          AI-powered cycling training platform
        </p>
        {/* Google renders its own button here */}
        <div ref={buttonRef} className="inline-block" />
        {/* Fallback if GSI button doesn't render */}
        <button
          onClick={login}
          className="mt-4 block mx-auto text-text-muted text-xs hover:text-text underline"
        >
          Or click here to sign in
        </button>
      </div>
    </div>
  )
}
