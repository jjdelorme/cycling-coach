import { useState, useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useNutritionistChat, useNutritionSessions } from '../hooks/useApi'
import { fetchNutritionSession } from '../lib/api'
import {
  UtensilsCrossed,
  Send,
  History,
  RefreshCw,
  User as UserIcon,
  ChevronRight,
  AlertCircle,
  X,
  Quote,
} from 'lucide-react'

interface Props {
  initialContext?: string
  initialSessionId?: string
  // Increments every time the user clicks "Ask Nutritionist" (etc.) so we
  // can react to a follow-up open even when initialContext is unchanged.
  requestNonce?: number
}

interface Message {
  role: 'user' | 'assistant' | 'rate-limited'
  content: string  // for 'rate-limited': the full message that was sent to the agent (for retry)
  display?: string // for 'rate-limited': what to show as the user bubble on retry
}

export default function NutritionistPanel({ initialContext, initialSessionId, requestNonce }: Props) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [pendingContext, setPendingContext] = useState<string | undefined>()
  const [sessionId, setSessionId] = useState<string | undefined>()
  const [loadingSession, setLoadingSession] = useState(false)
  const [showAllSessions, setShowAllSessions] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const chat = useNutritionistChat()
  const { data: sessions } = useNutritionSessions()
  const consumedRequestRef = useRef<number | undefined>(undefined)
  const loadedSessionRef = useRef(false)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Consume each open() request from the nutritionist-handoff provider:
  //   - If the panel is empty (fresh chat), just swap the chip in place.
  //   - If a conversation is already in flight, start a new session so the
  //     new question is not tangled up with the previous thread, then show
  //     the chip in the fresh chat.
  // Tracks `requestNonce` rather than `initialContext` so a repeat click on
  // the same meal still re-opens cleanly instead of being deduped to a no-op.
  useEffect(() => {
    if (!initialContext) return
    if (requestNonce === undefined || requestNonce === consumedRequestRef.current) return
    consumedRequestRef.current = requestNonce

    if (messages.length > 0) {
      setMessages([])
      setSessionId(undefined)
      setInput('')
    }
    setPendingContext(initialContext)
    textareaRef.current?.focus()
    // Intentionally omit `messages` from deps: the messages array changes
    // constantly during chat, but we only want to act when a new request
    // arrives. The branch above reads the current value at request time.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestNonce, initialContext])

  // Auto-load session if initialSessionId is provided (from quick-log "Chat about this")
  useEffect(() => {
    if (initialSessionId && !loadedSessionRef.current) {
      loadedSessionRef.current = true
      setLoadingSession(true)
      fetchNutritionSession(initialSessionId)
        .then(detail => {
          setSessionId(initialSessionId)
          const loaded: Message[] = detail.messages
            .filter(m => m.content_text)
            .map(m => ({
              role: m.role === 'user' ? 'user' as const : 'assistant' as const,
              content: m.content_text!,
            }))
          setMessages(loaded)
        })
        .finally(() => setLoadingSession(false))
    }
  }, [initialSessionId])

  const sendMessage = async (displayMsg: string, agentMsg?: string) => {
    if (!displayMsg.trim() || chat.isPending) return
    const toSend = (agentMsg ?? displayMsg).trim()
    setMessages(prev => [...prev, { role: 'user', content: displayMsg.trim() }])

    try {
      const res = await chat.mutateAsync({ message: toSend, session_id: sessionId })
      setSessionId(res.session_id)
      setMessages(prev => [...prev, { role: 'assistant', content: res.response }])
    } catch (err) {
      const isRateLimit = err instanceof Error && err.message.toLowerCase().includes('rate limit')
      setMessages(prev => [...prev,
        isRateLimit
          ? { role: 'rate-limited' as const, content: toSend, display: displayMsg.trim() }
          : { role: 'assistant', content: 'Error getting response. Please try again.' }
      ])
    }
  }

  const retryMessage = async (failed: Message) => {
    const toSend = failed.content
    const displayMsg = failed.display ?? failed.content
    setMessages(prev => prev.filter(m => m.role !== 'rate-limited'))
    setMessages(prev => [...prev, { role: 'user', content: displayMsg }])
    try {
      const res = await chat.mutateAsync({ message: toSend, session_id: sessionId })
      setSessionId(res.session_id)
      setMessages(prev => [...prev, { role: 'assistant', content: res.response }])
    } catch (err) {
      const isRateLimit = err instanceof Error && err.message.toLowerCase().includes('rate limit')
      setMessages(prev => [...prev,
        isRateLimit
          ? { role: 'rate-limited' as const, content: toSend, display: displayMsg }
          : { role: 'assistant', content: 'Error getting response. Please try again.' }
      ])
    }
  }

  const send = () => {
    if (!input.trim()) return
    const displayMsg = input.trim()
    const agentMsg = pendingContext
      ? `Context:\n${pendingContext}\n\nQuestion: ${displayMsg}`
      : displayMsg
    setInput('')
    setPendingContext(undefined)
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
    sendMessage(displayMsg, agentMsg)
  }

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      {/* Recent sessions */}
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
                    const detail = await fetchNutritionSession(s.session_id)
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
                className="group flex items-center justify-between w-full px-3 py-2 bg-surface border border-border rounded-lg text-xs text-text-muted hover:text-text hover:border-green hover:bg-surface-high transition-all shadow-sm"
              >
                <span className="truncate pr-4 font-medium">{s.title || 'Untitled Session'}</span>
                <ChevronRight size={12} className="opacity-0 group-hover:opacity-100 transition-opacity text-green" />
              </button>
            ))}
          </div>
          {sessions.length > 4 && (
            <button
              onClick={() => setShowAllSessions(prev => !prev)}
              className="w-full text-center text-[10px] font-bold uppercase tracking-widest text-text-muted hover:text-green mt-3 py-1 transition-colors"
            >
              {showAllSessions ? 'Show Less' : 'Show More'}
            </button>
          )}
        </div>
      )}

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-5 py-6 space-y-6 bg-surface">
        {loadingSession && (
          <div className="flex flex-col items-center justify-center py-12 space-y-3">
            <RefreshCw size={24} className="animate-spin text-green opacity-40" />
            <p className="text-[10px] font-bold text-text-muted uppercase tracking-widest italic">Restoring context...</p>
          </div>
        )}

        {messages.length === 0 && !loadingSession && (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <div className="w-16 h-16 bg-surface-low rounded-full flex items-center justify-center mb-4 border border-border">
              <UtensilsCrossed size={24} className="text-green opacity-20" />
            </div>
            <p className="text-sm font-bold text-text uppercase tracking-widest mb-1">Nutritionist is ready</p>
            <p className="text-xs text-text-muted font-medium px-8 leading-relaxed">
              Ask about meal planning, fueling strategy, or macro targets.
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
                    onClick={() => retryMessage(m)}
                    disabled={chat.isPending}
                    className="flex items-center gap-1.5 text-xs font-bold text-green hover:opacity-80 disabled:opacity-40 transition-opacity"
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
                    ? 'bg-green/10 border-green/20 text-green'
                    : 'bg-surface-high border-border text-text-muted'
                }`}>
                  {m.role === 'user' ? <UserIcon size={14} /> : <UtensilsCrossed size={14} />}
                </div>
                <div className={`max-w-[85%] text-sm leading-relaxed ${
                  m.role === 'user'
                    ? 'bg-green text-white rounded-2xl rounded-tr-none px-4 py-2.5 shadow-md shadow-green/10'
                    : 'text-text'
                }`}>
                  {m.role === 'assistant' ? (
                    <div className="prose prose-sm prose-invert max-w-none
                      [&_p]:my-1.5 [&_ul]:my-2 [&_li]:my-1 [&_strong]:text-green [&_strong]:font-bold
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
              <UtensilsCrossed size={14} />
            </div>
            <div className="flex items-center gap-1 px-4 py-2 text-text-muted italic text-xs bg-surface-low rounded-2xl rounded-tl-none">
              <span className="w-1.5 h-1.5 bg-green rounded-full animate-bounce [animation-delay:-0.3s]" />
              <span className="w-1.5 h-1.5 bg-green rounded-full animate-bounce [animation-delay:-0.15s]" />
              <span className="w-1.5 h-1.5 bg-green rounded-full animate-bounce" />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      <div className="p-5 bg-surface-low border-t border-border">
        {pendingContext && (
          <div className="mb-2 flex items-start gap-2 px-3 py-2 bg-surface border-l-2 border-accent rounded-md text-xs text-text-muted shadow-sm">
            <Quote size={12} className="text-accent shrink-0 mt-0.5" />
            <div
              className="flex-1 whitespace-pre-wrap line-clamp-3 leading-snug"
              title={pendingContext}
            >
              {pendingContext}
            </div>
            <button
              onClick={() => setPendingContext(undefined)}
              aria-label="Remove context"
              className="shrink-0 text-text-muted hover:text-text transition-colors p-0.5 -mr-0.5 -mt-0.5"
            >
              <X size={12} />
            </button>
          </div>
        )}
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
            placeholder={pendingContext ? 'Type your question about this...' : 'Ask your nutritionist...'}
            rows={1}
            className="w-full bg-surface text-text border border-border rounded-xl px-4 py-3.5 pr-12 text-sm placeholder:text-text-muted/40 focus:outline-none focus:border-green focus:ring-1 focus:ring-green/20 transition-all shadow-sm resize-none overflow-y-auto"
            style={{ maxHeight: 150 }}
          />
          <button
            onClick={send}
            disabled={chat.isPending || !input.trim()}
            className="absolute right-2.5 bottom-2.5 p-2 bg-green text-white rounded-lg disabled:opacity-30 disabled:grayscale hover:opacity-90 active:scale-95 transition-all shadow-lg shadow-green/20"
          >
            {chat.isPending ? <RefreshCw size={16} className="animate-spin" /> : <Send size={16} />}
          </button>
        </div>
        <p className="text-[9px] font-bold text-text-muted uppercase tracking-widest mt-2 text-center opacity-30">Press Enter to send</p>
      </div>
    </div>
  )
}
