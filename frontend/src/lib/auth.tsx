import { createContext, useContext, useState, useCallback, useEffect, useRef, type ReactNode } from 'react'
import { GoogleOAuthProvider, googleLogout } from '@react-oauth/google'
import { exchangeGoogleToken } from './api'

interface AuthUser {
  email: string
  name: string
  avatar: string
  role: string
}

interface AuthContextType {
  user: AuthUser | null
  token: string | null
  isAuthenticated: boolean
  isLoading: boolean
  login: () => void
  logout: () => void
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  token: null,
  isAuthenticated: false,
  isLoading: true,
  login: () => {},
  logout: () => {},
})

export const useAuth = () => useContext(AuthContext)

// Get the token for API calls
let _getToken: () => string | null = () => null
export const getToken = () => _getToken()

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID || ''

function AuthProviderInner({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const gsiInitialized = useRef(false)

  // Expose token getter for api.ts
  _getToken = useCallback(() => token, [token])

  const setSession = useCallback((appToken: string, email: string, displayName: string, avatarUrl: string, role: string) => {
    setToken(appToken)
    sessionStorage.setItem('auth_token', appToken)
    setUser({
      email,
      name: displayName || email,
      avatar: avatarUrl || '',
      role,
    })
  }, [])

  const clearSession = useCallback(() => {
    setUser(null)
    setToken(null)
    sessionStorage.removeItem('auth_token')
  }, [])

  // Handle a Google credential by exchanging it for an app token
  const handleCredential = useCallback(async (googleIdToken: string) => {
    try {
      const data = await exchangeGoogleToken(googleIdToken)
      setSession(data.token, data.email, data.display_name, data.avatar_url, data.role)
    } catch {
      clearSession()
    }
  }, [setSession, clearSession])

  // Restore an existing app token from sessionStorage
  const restoreSession = useCallback(async (appToken: string) => {
    try {
      const res = await fetch('/api/users/me', {
        headers: { Authorization: `Bearer ${appToken}` },
      })
      if (res.ok) {
        const data = await res.json()
        setSession(appToken, data.email, data.display_name, data.avatar_url, data.role)
      } else {
        clearSession()
      }
    } catch {
      clearSession()
    }
  }, [setSession, clearSession])

  // On mount: try to restore session, then initialize GSI
  useEffect(() => {
    if (!GOOGLE_CLIENT_ID) {
      // Dev mode
      setUser({ email: 'dev@localhost', name: 'Dev User', avatar: '', role: 'admin' })
      setToken('dev-mode')
      setIsLoading(false)
      return
    }

    if (gsiInitialized.current) {
      setIsLoading(false)
      return
    }

    // Try to restore from sessionStorage
    const stored = sessionStorage.getItem('auth_token')
    if (stored) {
      restoreSession(stored).then(() => setIsLoading(false))
    }

    // Initialize GSI for fresh logins and token refresh
    const waitForGsi = setInterval(() => {
      if (window.google?.accounts?.id) {
        clearInterval(waitForGsi)
        gsiInitialized.current = true

        window.google.accounts.id.initialize({
          client_id: GOOGLE_CLIENT_ID,
          callback: (response: { credential: string }) => {
            handleCredential(response.credential)
          },
          auto_select: true,
        })

        if (!stored) setIsLoading(false)
      }
    }, 100)

    const timeout = setTimeout(() => {
      clearInterval(waitForGsi)
      setIsLoading(false)
    }, 5000)

    return () => {
      clearInterval(waitForGsi)
      clearTimeout(timeout)
    }
  }, [handleCredential, restoreSession])

  const login = useCallback(() => {
    if (window.google?.accounts?.id) {
      window.google.accounts.id.prompt()
    }
  }, [])

  const logout = useCallback(() => {
    googleLogout()
    clearSession()
  }, [clearSession])

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isAuthenticated: !!user,
        isLoading,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function AuthProvider({ children }: { children: ReactNode }) {
  if (!GOOGLE_CLIENT_ID) {
    return <AuthProviderInner>{children}</AuthProviderInner>
  }

  return (
    <GoogleOAuthProvider clientId={GOOGLE_CLIENT_ID}>
      <AuthProviderInner>{children}</AuthProviderInner>
    </GoogleOAuthProvider>
  )
}

// Type augmentation for Google Identity Services
declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: {
            client_id: string
            callback: (response: { credential: string }) => void
            auto_select?: boolean
          }) => void
          prompt: (notification?: (n: { isNotDisplayed: () => boolean }) => void) => void
          renderButton: (element: HTMLElement, config: Record<string, unknown>) => void
          revoke: (hint: string, callback?: () => void) => void
        }
      }
    }
  }
}
