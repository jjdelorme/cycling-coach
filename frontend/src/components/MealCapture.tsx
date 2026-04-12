import { useRef, useState, useEffect } from 'react'
import { Camera, Loader2, Mic, MicOff, MessageSquare, Plus, X, Send, UtensilsCrossed } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useLogMeal, useNutritionistChat } from '../hooks/useApi'
import MacroAnalysisCard from './MacroAnalysisCard'
import type { MealDetail } from '../types/api'

interface Props {
  onMealSaved?: (meal: MealDetail) => void
  onOpenNutritionist?: (context?: string, sessionId?: string) => void
}

export default function MealCapture({ onMealSaved, onOpenNutritionist }: Props) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [expanded, setExpanded] = useState(false)
  const logMeal = useLogMeal()

  // Quick-log modal state
  const [textModalOpen, setTextModalOpen] = useState(false)
  const [quickInput, setQuickInput] = useState('')
  const [quickUserMsg, setQuickUserMsg] = useState('')
  const [quickResponse, setQuickResponse] = useState<string | null>(null)
  const [quickSessionId, setQuickSessionId] = useState<string | undefined>()
  const quickChat = useNutritionistChat()
  const quickInputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (textModalOpen && !quickResponse && !quickChat.isPending) {
      setTimeout(() => quickInputRef.current?.focus(), 100)
    }
  }, [textModalOpen, quickResponse, quickChat.isPending])

  const handleQuickSend = async () => {
    if (!quickInput.trim() || quickChat.isPending) return
    const msg = quickInput.trim()
    setQuickUserMsg(msg)
    setQuickInput('')

    try {
      const res = await quickChat.mutateAsync({
        message: `Log this meal: ${msg}`,
      })
      setQuickSessionId(res.session_id)
      setQuickResponse(res.response)
    } catch {
      setQuickResponse('Error logging meal. Please try again.')
    }
  }

  const closeQuickLog = () => {
    setTextModalOpen(false)
    setQuickInput('')
    setQuickUserMsg('')
    setQuickResponse(null)
    setQuickSessionId(undefined)
  }

  const handleChatAboutMeal = () => {
    const sid = quickSessionId
    closeQuickLog()
    onOpenNutritionist?.(undefined, sid)
  }

  // Voice recording state
  const [recording, setRecording] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const [audioBlob, setAudioBlob] = useState<{ blob: Blob; mime: string } | null>(null)

  const handleCapture = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setExpanded(false)
    setPreview(URL.createObjectURL(file))

    try {
      const result = await logMeal.mutateAsync({
        file,
        audio: audioBlob?.blob,
        audioMimeType: audioBlob?.mime,
      })
      onMealSaved?.(result)
      setPreview(null)
      setAudioBlob(null)
    } catch {
      // preview stays set → card remains mounted → error prop is shown
    } finally {
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/mp4'
      const recorder = new MediaRecorder(stream, { mimeType })
      chunksRef.current = []

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }
      recorder.onstop = () => {
        stream.getTracks().forEach(t => t.stop())
        if (timerRef.current) clearInterval(timerRef.current)
        const blob = new Blob(chunksRef.current, { type: mimeType.split(';')[0] })
        setAudioBlob({ blob, mime: mimeType.split(';')[0] })
        setElapsed(0)
      }

      recorderRef.current = recorder
      recorder.start()
      setRecording(true)
      setElapsed(0)
      timerRef.current = setInterval(() => {
        setElapsed(prev => {
          if (prev + 1 >= 15) {
            recorder.stop()
            setRecording(false)
            return 0
          }
          return prev + 1
        })
      }, 1000)
    } catch {
      // Microphone permission denied
    }
  }

  const stopRecording = () => {
    if (recorderRef.current && recorderRef.current.state === 'recording') {
      recorderRef.current.stop()
      setRecording(false)
    }
  }

  return (
    <>
      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        onChange={handleCapture}
        className="hidden"
      />

      {/* Analysis card shown during upload */}
      {(preview || logMeal.isPending) && (
        <MacroAnalysisCard
          photoUrl={preview}
          isPending={logMeal.isPending}
          error={logMeal.error?.message}
          onCancel={() => {
            setPreview(null)
            if (fileRef.current) fileRef.current.value = ''
          }}
        />
      )}

      {/* Backdrop when expanded */}
      {expanded && (
        <div
          className="fixed inset-0 z-20"
          onClick={() => setExpanded(false)}
        />
      )}

      {/* Log a Meal FAB */}
      <div className="fixed bottom-24 left-6 md:bottom-8 md:left-8 z-30">
        {/* Expanded options */}
        {expanded && (
          <div className="absolute bottom-16 left-0 flex flex-col gap-2 animate-in fade-in slide-in-from-bottom-2 duration-200">
            {/* Photo option */}
            <button
              onClick={() => { fileRef.current?.click() }}
              disabled={logMeal.isPending}
              className="flex items-center gap-3 px-4 py-2.5 bg-surface border border-border rounded-xl shadow-lg hover:bg-surface-high transition-all whitespace-nowrap"
            >
              <div className="w-8 h-8 bg-accent/10 rounded-lg flex items-center justify-center">
                <Camera size={16} className="text-accent" />
              </div>
              <span className="text-sm font-bold text-text">Photo</span>
            </button>

            {/* Voice option */}
            <button
              onPointerDown={startRecording}
              onPointerUp={stopRecording}
              onPointerLeave={stopRecording}
              className={`flex items-center gap-3 px-4 py-2.5 border rounded-xl shadow-lg transition-all whitespace-nowrap ${
                recording
                  ? 'bg-red/10 border-red/30 animate-pulse'
                  : 'bg-surface border-border hover:bg-surface-high'
              }`}
            >
              <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${
                recording ? 'bg-red/20' : 'bg-green/10'
              }`}>
                {recording ? <MicOff size={16} className="text-red" /> : <Mic size={16} className="text-green" />}
              </div>
              <span className="text-sm font-bold text-text">
                {recording ? `Recording ${elapsed}s` : 'Voice'}
              </span>
              {audioBlob && !recording && (
                <span className="w-2 h-2 bg-green rounded-full" />
              )}
            </button>

            {/* Text option */}
            <button
              onClick={() => {
                setExpanded(false)
                setTextModalOpen(true)
              }}
              className="flex items-center gap-3 px-4 py-2.5 bg-surface border border-border rounded-xl shadow-lg hover:bg-surface-high transition-all whitespace-nowrap"
            >
              <div className="w-8 h-8 bg-blue/10 rounded-lg flex items-center justify-center">
                <MessageSquare size={16} className="text-blue" />
              </div>
              <span className="text-sm font-bold text-text">Text</span>
            </button>
          </div>
        )}

        {/* Main pill button */}
        <button
          onClick={() => setExpanded(!expanded)}
          disabled={logMeal.isPending}
          className={`flex items-center gap-2 px-5 py-3 rounded-full shadow-lg transition-all disabled:opacity-50 ${
            expanded
              ? 'bg-surface text-text border border-border shadow-xl'
              : 'bg-accent text-white shadow-accent/20 hover:opacity-90 active:scale-95'
          }`}
        >
          {logMeal.isPending ? (
            <Loader2 size={18} className="animate-spin" />
          ) : expanded ? (
            <X size={18} />
          ) : (
            <Plus size={18} />
          )}
          <span className="text-xs font-bold uppercase tracking-widest">Log a Meal</span>
        </button>
      </div>

      {/* Quick-log text modal */}
      {textModalOpen && (
        <>
          <div className="fixed inset-0 bg-black/50 z-40" onClick={!quickChat.isPending ? closeQuickLog : undefined} />
          <div className="fixed bottom-0 left-0 right-0 rounded-t-2xl md:bottom-auto md:left-1/2 md:top-1/2 md:-translate-x-1/2 md:-translate-y-1/2 md:w-full md:max-w-md md:rounded-2xl z-50 bg-surface border border-border shadow-2xl flex flex-col max-h-[80vh]">
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-border">
              <div className="flex items-center gap-2">
                <UtensilsCrossed size={16} className="text-green" />
                <span className="text-sm font-bold text-text uppercase tracking-wider">Log a Meal</span>
              </div>
              <button onClick={closeQuickLog} disabled={quickChat.isPending} className="p-1.5 text-text-muted hover:text-text rounded-md transition-colors disabled:opacity-30">
                <X size={16} />
              </button>
            </div>

            <div className="px-4 py-4">
              {/* State 1: Input */}
              {!quickUserMsg && (
                <div className="relative">
                  <textarea
                    ref={quickInputRef}
                    value={quickInput}
                    onChange={e => {
                      setQuickInput(e.target.value)
                      e.target.style.height = 'auto'
                      e.target.style.height = Math.min(e.target.scrollHeight, 100) + 'px'
                    }}
                    onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleQuickSend() } }}
                    placeholder="Describe what you ate..."
                    rows={2}
                    className="w-full bg-surface-low text-text border border-border rounded-xl px-3 py-2.5 pr-10 text-sm placeholder:text-text-muted/40 focus:outline-none focus:border-green focus:ring-1 focus:ring-green/20 transition-all resize-none"
                    style={{ maxHeight: 100 }}
                  />
                  <button
                    onClick={handleQuickSend}
                    disabled={!quickInput.trim()}
                    className="absolute right-2 bottom-2 p-1.5 bg-green text-white rounded-lg disabled:opacity-30 hover:opacity-90 active:scale-95 transition-all"
                  >
                    <Send size={14} />
                  </button>
                </div>
              )}

              {/* State 2: Processing */}
              {quickUserMsg && !quickResponse && (
                <div className="flex flex-col items-center py-6 space-y-4">
                  <p className="text-sm text-text-muted italic text-center px-4">"{quickUserMsg}"</p>
                  <Loader2 size={28} className="text-green animate-spin" />
                  <p className="text-[10px] font-bold text-text-muted uppercase tracking-widest">Logging meal...</p>
                </div>
              )}

              {/* State 3: Result */}
              {quickResponse && (
                <div className="space-y-4">
                  <div className="bg-surface-low rounded-xl px-4 py-3 border border-border">
                    <div className="prose prose-sm prose-invert max-w-none [&_p]:my-1 [&_strong]:text-green coach-prose text-sm text-text">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{quickResponse}</ReactMarkdown>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    {onOpenNutritionist && (
                      <button
                        onClick={handleChatAboutMeal}
                        className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-surface-low border border-border rounded-xl text-sm font-bold text-text-muted hover:text-text hover:border-green transition-all"
                      >
                        <MessageSquare size={14} />
                        Chat about this
                      </button>
                    )}
                    <button
                      onClick={closeQuickLog}
                      className="flex-1 px-4 py-2.5 bg-green text-white rounded-xl text-sm font-bold hover:opacity-90 active:scale-[0.98] transition-all"
                    >
                      Done
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </>
  )
}
