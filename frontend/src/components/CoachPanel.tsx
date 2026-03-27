import { useState, useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import { useSendChat, useSessions } from '../hooks/useApi'
import { fetchSession } from '../lib/api'
import type { ViewContext } from './Layout'

interface Props {
  onClose: () => void
  viewContext?: ViewContext
}

interface Message {
  role: 'user' | 'assistant'
  content: string
}

function buildViewHint(ctx?: ViewContext): string {
  if (!ctx) return ''
  const parts: string[] = []
  switch (ctx.tab) {
    case 'dashboard':
      parts.push('Viewing: Dashboard')
      break
    case 'rides':
      if (ctx.rideId) parts.push(`Viewing: Ride #${ctx.rideId}`)
      else if (ctx.rideDate) parts.push(`Viewing: Workout on ${ctx.rideDate}`)
      else parts.push('Viewing: Rides list')
      break
    case 'calendar':
      parts.push('Viewing: Calendar')
      break
    case 'analysis':
      parts.push('Viewing: Analysis')
      break
    case 'settings':
      parts.push('Viewing: Settings')
      break
  }
  return parts.length > 0 ? `[${parts.join(', ')}]\n` : ''
}

export default function CoachPanel({ onClose, viewContext }: Props) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [sessionId, setSessionId] = useState<string | undefined>()
  const [loadingSession, setLoadingSession] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const chat = useSendChat()
  const { data: sessions } = useSessions()

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

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
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Error getting response. Please try again.' }])
    }
  }

  const newSession = () => {
    setMessages([])
    setSessionId(undefined)
  }

  return (
    <aside className="w-full md:w-[400px] border-l border-border bg-surface flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <h3 className="font-semibold text-sm">AI Coach</h3>
        <div className="flex items-center gap-2">
          <button onClick={newSession} className="text-xs text-text-muted hover:text-text">
            New Chat
          </button>
          <button onClick={onClose} className="text-text-muted hover:text-text text-lg leading-none">
            &times;
          </button>
        </div>
      </div>

      {/* Sessions */}
      {messages.length === 0 && sessions && sessions.length > 0 && (
        <div className="border-b border-border px-4 py-2 max-h-32 overflow-y-auto">
          <p className="text-xs text-text-muted mb-1">Recent sessions:</p>
          {sessions.slice(0, 5).map(s => (
            <button
              key={s.session_id}
              onClick={async () => {
                setLoadingSession(true)
                try {
                  const detail = await fetchSession(s.session_id)
                  setSessionId(s.session_id)
                  const loaded: Message[] = []
                  for (const m of detail.messages) {
                    if (m.content_text) {
                      loaded.push({
                        role: m.role === 'user' ? 'user' : 'assistant',
                        content: m.content_text,
                      })
                    }
                  }
                  setMessages(loaded)
                } finally {
                  setLoadingSession(false)
                }
              }}
              className="block text-xs text-blue hover:underline truncate w-full text-left py-0.5"
            >
              {s.title || s.session_id}
            </button>
          ))}
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
        {loadingSession && (
          <div className="text-text-muted text-sm text-center mt-8 animate-pulse">Loading session...</div>
        )}
        {messages.length === 0 && !loadingSession && (
          <p className="text-text-muted text-sm text-center mt-8">
            Ask your coach about training, ride analysis, or plan adjustments.
          </p>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className={`text-sm ${
              m.role === 'user'
                ? 'bg-surface2 rounded-lg px-3 py-2 ml-8'
                : 'pr-8'
            }`}
          >
            {m.role === 'assistant' ? (
              <div className="prose prose-sm prose-invert max-w-none [&_p]:my-1 [&_ul]:my-1 [&_li]:my-0.5">
                <ReactMarkdown>{m.content}</ReactMarkdown>
              </div>
            ) : (
              m.content
            )}
          </div>
        ))}
        {chat.isPending && (
          <div className="text-text-muted text-sm animate-pulse">Thinking...</div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="border-t border-border p-3">
        <div className="flex gap-2 items-end">
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
            className="flex-1 bg-bg border border-border rounded-md px-3 py-2 text-sm text-text placeholder:text-text-muted focus:outline-none focus:border-accent resize-none overflow-y-auto"
            style={{ maxHeight: 150 }}
          />
          <button
            onClick={send}
            disabled={chat.isPending || !input.trim()}
            className="bg-accent text-white px-3 py-2 rounded-md text-sm font-medium disabled:opacity-50 hover:opacity-90 transition-opacity"
          >
            Send
          </button>
        </div>
      </div>
    </aside>
  )
}
