import { useEffect, useRef } from 'react'
import { useAuth } from '../lib/auth'
import { Bike, ShieldAlert, Clock, ChevronRight } from 'lucide-react'

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
          shape: 'pill',
        })
      }
    }, 100)
    const timeout = setTimeout(() => clearInterval(interval), 5000)
    return () => { clearInterval(interval); clearTimeout(timeout) }
  }, [])

  // Authenticated but no access (role === 'none')
  if (isAuthenticated && user?.role === 'none') {
    return (
      <div className="flex items-center justify-center min-h-screen bg-bg p-6">
        <div className="text-center max-w-sm w-full bg-surface border border-border p-10 rounded-3xl shadow-2xl animate-in zoom-in duration-500">
          <div className="w-20 h-20 bg-accent/10 rounded-full flex items-center justify-center mx-auto mb-6 border border-accent/20">
            <ShieldAlert size={40} className="text-accent" />
          </div>
          <h1 className="text-2xl font-bold text-text mb-3 uppercase tracking-tight">Access Restricted</h1>
          <div className="space-y-4 mb-8">
            <p className="text-text-muted text-sm leading-relaxed">
              Signed in as <span className="text-text font-bold block mt-1">{user.email}</span>
            </p>
            <p className="text-text-muted text-xs font-medium bg-surface-low p-4 rounded-xl border border-border/50">
              An administrator needs to authorize your account before you can access the platform.
            </p>
          </div>
          <button
            onClick={() => window.location.reload()}
            className="w-full flex items-center justify-center gap-2 px-6 py-3 bg-accent text-white rounded-xl text-xs font-bold uppercase tracking-widest hover:opacity-90 transition-all shadow-lg shadow-accent/20"
          >
            <Clock size={14} /> Refresh Status
          </button>
        </div>
      </div>
    )
  }

  // Not authenticated — show login
  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-bg p-6 relative overflow-hidden">
      {/* Decorative background element */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-accent/5 rounded-full blur-[120px] -z-10" />
      
      <div className="text-center max-w-sm w-full bg-surface border border-border p-12 rounded-[2.5rem] shadow-2xl animate-in fade-in slide-in-from-bottom-8 duration-700">
        <div className="w-24 h-24 bg-accent rounded-[2rem] flex items-center justify-center mx-auto mb-8 shadow-xl shadow-accent/30 rotate-3">
          <Bike size={48} className="text-white -rotate-3" />
        </div>
        
        <h1 className="text-3xl font-bold text-text mb-2 tracking-tighter uppercase">Coach</h1>
        <p className="text-text-muted text-sm font-medium mb-10 tracking-wide opacity-60">
          AI PERFORMANCE ENGINE
        </p>
        
        <div className="flex flex-col items-center gap-6">
          <div ref={buttonRef} className="inline-block" />
          
          <button
            onClick={login}
            className="group flex items-center gap-2 text-text-muted text-[10px] font-bold uppercase tracking-[0.2em] hover:text-accent transition-colors"
          >
            Manual Entry <ChevronRight size={12} className="group-hover:translate-x-1 transition-transform" />
          </button>
        </div>
      </div>
      
      <p className="mt-12 text-[10px] font-bold text-text-muted uppercase tracking-[0.3em] opacity-20">Version {__APP_VERSION__}</p>
    </div>
  )
}
