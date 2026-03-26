import { createContext, useContext, useState, useCallback, useEffect, useRef, type ReactNode } from 'react'
import { GoogleOAuthProvider, googleLogout } from '@react-oauth/google'

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

  // Handle a credential (JWT ID token) from Google
  const handleCredential = useCallback(async (idToken: string) => {
    setToken(idToken)
    try {
      const res = await fetch('/api/users/me', {
        headers: { Authorization: `Bearer ${idToken}` },
      })
      if (res.ok) {
        const data = await res.json()
        setUser({
          email: data.email,
          name: data.display_name || data.email,
          avatar: data.avatar_url || '',
          role: data.role,
        })
      } else {
        setUser(null)
        setToken(null)
      }
    } catch {
      setUser(null)
      setToken(null)
    }
  }, [])

  // Initialize Google Identity Services for the credential (JWT) flow
  useEffect(() => {
    if (!GOOGLE_CLIENT_ID || gsiInitialized.current) {
      if (!GOOGLE_CLIENT_ID) {
        // Dev mode
        setUser({ email: 'dev@localhost', name: 'Dev User', avatar: '', role: 'admin' })
        setToken('dev-mode')
      }
      setIsLoading(false)
      return
    }

    // Wait for the GSI script to load (loaded by @react-oauth/google)
    const waitForGsi = setInterval(() => {
      if (window.google?.accounts?.id) {
        clearInterval(waitForGsi)
        gsiInitialized.current = true

        window.google.accounts.id.initialize({
          client_id: GOOGLE_CLIENT_ID,
          callback: (response: { credential: string }) => {
            handleCredential(response.credential)
          },
          auto_select: true, // silent re-auth if user previously signed in
        })

        setIsLoading(false)
      }
    }, 100)

    // Timeout after 5s
    const timeout = setTimeout(() => {
      clearInterval(waitForGsi)
      setIsLoading(false)
    }, 5000)

    return () => {
      clearInterval(waitForGsi)
      clearTimeout(timeout)
    }
  }, [handleCredential])

  const login = useCallback(() => {
    if (window.google?.accounts?.id) {
      window.google.accounts.id.prompt()
    }
  }, [])

  const logout = useCallback(() => {
    googleLogout()
    setUser(null)
    setToken(null)
  }, [])

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
