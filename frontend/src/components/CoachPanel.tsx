import { useState, useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useSendChat, useSessions } from '../hooks/useApi'
import { fetchSession } from '../lib/api'
import NutritionistPanel from './NutritionistPanel'
import type { ViewContext } from './Layout'
import {
  Bot,
  X,
  Plus,
  Send,
  History,
  MessageSquare,
  RefreshCw,
  User as UserIcon,
  ChevronRight,
  UtensilsCrossed,
  AlertCircle,
} from 'lucide-react'

interface Props {
  onClose: () => void
  viewContext?: ViewContext
  nutritionistContext?: string
}

interface Message {
  role: 'user' | 'assistant' | 'rate-limited'
  content: string  // for 'rate-limited': stores original user message for retry
}

function buildViewHint(ctx?: ViewContext): string {
  if (!ctx) return ''
  const parts: string[] = []
  switch (ctx.tab) {
    case 'dashboard': parts.push('Viewing: Dashboard'); break
    case 'rides':
      if (ctx.rideId) parts.push(`Viewing: Ride #${ctx.rideId}`)
      else if (ctx.rideDate) parts.push(`Viewing: Workout on ${ctx.rideDate}`)
      else parts.push('Viewing: Rides list')
      break
    case 'calendar': 
      if (ctx.calendarDate) parts.push(`Viewing: Calendar (selected day: ${ctx.calendarDate})`)
      else parts.push('Viewing: Calendar')
      break
    case 'analysis': parts.push('Viewing: Analysis'); break
    case 'nutrition': parts.push('Viewing: Nutrition'); break
    case 'settings': parts.push('Viewing: Settings'); break
  }
  return parts.length > 0 ? `[${parts.join(', ')}]\n` : ''
}

export default function CoachPanel({ onClose, viewContext, nutritionistContext }: Props) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [sessionId, setSessionId] = useState<string | undefined>()
  const [loadingSession, setLoadingSession] = useState(false)
  const [showAllSessions, setShowAllSessions] = useState(false)
  const [agentTab, setAgentTab] = useState<'coach' | 'nutritionist'>('coach')
  const [nutritionistKey, setNutritionistKey] = useState(0)
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const chat = useSendChat()
  const { data: sessions } = useSessions()

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    if (nutritionistContext) setAgentTab('nutritionist')
  }, [nutritionistContext])

  const send = async () => {
    if (!input.trim() || chat.isPending) return
    const msg = input.trim()
    setInput('')
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
    setMessages(prev => [...prev, { role: 'user', content: msg }])

    try {
      const hint = buildViewHint(viewContext)
      const res = await chat.mutateAsync({ message: hint + msg, session_id: sessionId })
      setSessionId(res.session_id)
      setMessages(prev => [...prev, { role: 'assistant', content: res.response }])
    } catch (err) {
      const isRateLimit = err instanceof Error && err.message.toLowerCase().includes('rate limit')
      setMessages(prev => [...prev,
        isRateLimit
          ? { role: 'rate-limited' as const, content: msg }
          : { role: 'assistant', content: 'Error getting response. Please try again.' }
      ])
    }
  }

  const retrySend = async (originalMsg: string) => {
    setMessages(prev => prev.filter(m => m.role !== 'rate-limited'))
    setMessages(prev => [...prev, { role: 'user', content: originalMsg }])
    try {
      const hint = buildViewHint(viewContext)
      const res = await chat.mutateAsync({ message: hint + originalMsg, session_id: sessionId })
      setSessionId(res.session_id)
      setMessages(prev => [...prev, { role: 'assistant', content: res.response }])
    } catch (err) {
      const isRateLimit = err instanceof Error && err.message.toLowerCase().includes('rate limit')
      setMessages(prev => [...prev,
        isRateLimit
          ? { role: 'rate-limited' as const, content: originalMsg }
          : { role: 'assistant', content: 'Error getting response. Please try again.' }
      ])
    }
  }

  const newSession = () => {
    if (agentTab === 'nutritionist') {
      setNutritionistKey(k => k + 1)
    } else {
      setMessages([])
      setSessionId(undefined)
    }
  }

  return (
    <aside className="w-full md:w-[400px] border-l border-border bg-surface flex flex-col h-full shadow-2xl z-20 animate-in slide-in-from-right duration-300">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-5 py-4 bg-surface-low">
        <div className="flex items-center gap-2.5">
          <div className="p-1.5 bg-accent/10 rounded-lg">
            <Bot size={18} className="text-accent" />
          </div>
          <h3 className="font-bold text-sm tracking-tight text-text uppercase">AI Coach</h3>
        </div>
        <div className="flex items-center gap-1">
          <button 
            onClick={newSession} 
            className="p-2 text-text-muted hover:text-accent hover:bg-accent/5 rounded-md transition-all"
            title="New Chat"
          >
            <Plus size={18} />
          </button>
          <button 
            onClick={onClose} 
            className="p-2 text-text-muted hover:text-red hover:bg-red/5 rounded-md transition-all"
          >
            <X size={18} />
          </button>
        </div>
      </div>

      {/* Agent tab switcher */}
      <div className="flex border-b border-border bg-surface-low/30 px-5 py-2 gap-2">
        <button
          onClick={() => setAgentTab('coach')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold uppercase tracking-widest transition-all ${
            agentTab === 'coach'
              ? 'bg-accent text-white'
              : 'text-text-muted hover:text-text'
          }`}
        >
          <Bot size={12} />
          Coach
        </button>
        <button
          onClick={() => setAgentTab('nutritionist')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold uppercase tracking-widest transition-all ${
            agentTab === 'nutritionist'
              ? 'bg-green text-white'
              : 'text-text-muted hover:text-text'
          }`}
        >
          <UtensilsCrossed size={12} />
          Nutritionist
        </button>
      </div>

      {agentTab === 'coach' && (
        <>
          {/* Recent Sessions */}
          {messages.length === 0 && sessions && sessions.length > 0 && (
            <div className="border-b border-border px-5 py-4 bg-surface-low/30">
              <div className="flex items-center gap-2 mb-3 text-text-muted">
                <History size={12} />
                <span className="text-[10px] font-bold uppercase tracking-widest">Recent Sessions</span>
              </div>
              <div className={`space-y-2 ${showAllSessions ? 'max-h-60 overflow-y-auto pr-1' : ''}`}>
                {sessions.slice(0, showAllSessions ? undefined : 4).map(s => (
                  <button
                    key={s.session_id}
                    onClick={async () => {
                      setLoadingSession(true)
                      try {
                        const detail = await fetchSession(s.session_id)
                        setSessionId(s.session_id)
                        const loaded: Message[] = detail.messages
                          .filter(m => m.content_text)
                          .map(m => ({
                            role: m.role === 'user' ? 'user' : 'assistant',
                            content: m.content_text!,
                          }))
                        setMessages(loaded)
                      } finally {
                        setLoadingSession(false)
                      }
                    }}
                    className="group flex items-center justify-between w-full px-3 py-2 bg-surface border border-border rounded-lg text-xs text-text-muted hover:text-text hover:border-accent hover:bg-surface-high transition-all shadow-sm"
                  >
                    <span className="truncate pr-4 font-medium">{s.title || 'Untitled Session'}</span>
                    <ChevronRight size={12} className="opacity-0 group-hover:opacity-100 transition-opacity text-accent" />
                  </button>
                ))}
              </div>
              {sessions.length > 4 && (
                <button
                  onClick={() => setShowAllSessions(prev => !prev)}
                  className="w-full text-center text-[10px] font-bold uppercase tracking-widest text-text-muted hover:text-accent mt-3 py-1 transition-colors"
                >
                  {showAllSessions ? 'Show Less' : 'Show More'}
                </button>
              )}
            </div>
          )}

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-5 py-6 space-y-6 bg-surface">
            {loadingSession && (
              <div className="flex flex-col items-center justify-center py-12 space-y-3">
                <RefreshCw size={24} className="animate-spin text-accent opacity-40" />
                <p className="text-[10px] font-bold text-text-muted uppercase tracking-widest italic">Restoring context...</p>
              </div>
            )}

            {messages.length === 0 && !loadingSession && (
              <div className="flex flex-col items-center justify-center py-12 text-center">
                <div className="w-16 h-16 bg-surface-low rounded-full flex items-center justify-center mb-4 border border-border">
                  <MessageSquare size={24} className="text-accent opacity-20" />
                </div>
                <p className="text-sm font-bold text-text uppercase tracking-widest mb-1">Coach is ready</p>
                <p className="text-xs text-text-muted font-medium px-8 leading-relaxed">
                  Ask about your recent performance, training load, or future objectives.
                </p>
              </div>
            )}

            {messages.map((m, i) => (
              <div key={i} className={`flex gap-3 ${m.role === 'user' ? 'flex-row-reverse' : ''}`}>
                {m.role === 'rate-limited' ? (
                  <div className="flex items-start gap-2.5 px-4 py-3 bg-yellow/10 border border-yellow/30 rounded-xl text-sm text-text max-w-[85%]">
                    <AlertCircle size={15} className="text-yellow shrink-0 mt-0.5" />
                    <div>
                      <p className="text-text-muted text-xs mb-2">The AI model is currently busy.</p>
                      <button
                        onClick={() => retrySend(m.content)}
                        disabled={chat.isPending}
                        className="flex items-center gap-1.5 text-xs font-bold text-accent hover:opacity-80 disabled:opacity-40 transition-opacity"
                      >
                        <RefreshCw size={12} className={chat.isPending ? 'animate-spin' : ''} />
                        Try Again
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    <div className={`shrink-0 w-8 h-8 rounded-full flex items-center justify-center border shadow-sm ${
                      m.role === 'user'
                        ? 'bg-accent/10 border-accent/20 text-accent'
                        : 'bg-surface-high border-border text-text-muted'
                    }`}>
                      {m.role === 'user' ? <UserIcon size={14} /> : <Bot size={14} />}
                    </div>
                    <div
                      className={`max-w-[85%] text-sm leading-relaxed ${
                        m.role === 'user'
                          ? 'bg-accent text-white rounded-2xl rounded-tr-none px-4 py-2.5 shadow-md shadow-accent/10'
                          : 'text-text'
                      }`}
                    >
                      {m.role === 'assistant' ? (
                        <div className="prose prose-sm prose-invert max-w-none
                          [&_p]:my-1.5 [&_ul]:my-2 [&_li]:my-1 [&_strong]:text-accent [&_strong]:font-bold
                          [&_code]:bg-surface-low [&_code]:px-1 [&_code]:rounded [&_code]:text-blue
                          coach-prose">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
                        </div>
                      ) : (
                        <p className="whitespace-pre-wrap">{m.content}</p>
                      )}
                    </div>
                  </>
                )}
              </div>
            ))}

            {chat.isPending && (
              <div className="flex gap-3 animate-pulse">
                <div className="shrink-0 w-8 h-8 rounded-full flex items-center justify-center bg-surface-high border border-border text-text-muted">
                  <Bot size={14} />
                </div>
                <div className="flex items-center gap-1 px-4 py-2 text-text-muted italic text-xs bg-surface-low rounded-2xl rounded-tl-none">
                  <span className="w-1.5 h-1.5 bg-accent rounded-full animate-bounce [animation-delay:-0.3s]"></span>
                  <span className="w-1.5 h-1.5 bg-accent rounded-full animate-bounce [animation-delay:-0.15s]"></span>
                  <span className="w-1.5 h-1.5 bg-accent rounded-full animate-bounce"></span>
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Input area */}
          <div className="p-5 bg-surface-low border-t border-border">
            <div className="relative group">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={e => {
                  setInput(e.target.value)
                  e.target.style.height = 'auto'
                  e.target.style.height = Math.min(e.target.scrollHeight, 150) + 'px'
                }}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
                placeholder="Ask your coach..."
                rows={1}
                className="w-full bg-surface text-text border border-border rounded-xl px-4 py-3.5 pr-12 text-sm placeholder:text-text-muted/40 focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/20 transition-all shadow-sm resize-none overflow-y-auto"
                style={{ maxHeight: 150 }}
              />
              <button
                onClick={send}
                disabled={chat.isPending || !input.trim()}
                className="absolute right-2.5 bottom-2.5 p-2 bg-accent text-white rounded-lg disabled:opacity-30 disabled:grayscale hover:opacity-90 active:scale-95 transition-all shadow-lg shadow-accent/20"
              >
                {chat.isPending ? <RefreshCw size={16} className="animate-spin" /> : <Send size={16} />}
              </button>
            </div>
            <p className="text-[9px] font-bold text-text-muted uppercase tracking-widest mt-2 text-center opacity-30">Press Enter to send • Shift+Enter for new line</p>
          </div>
        </>
      )}

      {agentTab === 'nutritionist' && (
        <NutritionistPanel key={nutritionistKey} initialContext={nutritionistContext} />
      )}
    </aside>
  )
}
