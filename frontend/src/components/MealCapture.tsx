import { useRef, useState } from 'react'
import { Camera, Loader2, Mic, MicOff, MessageSquare, Plus, X } from 'lucide-react'
import { useLogMeal } from '../hooks/useApi'
import MacroAnalysisCard from './MacroAnalysisCard'
import type { MealDetail } from '../types/api'

interface Props {
  onMealSaved?: (meal: MealDetail) => void
  onOpenNutritionist?: (context?: string) => void
}

export default function MealCapture({ onMealSaved, onOpenNutritionist }: Props) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [expanded, setExpanded] = useState(false)
  const logMeal = useLogMeal()

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
            {onOpenNutritionist && (
              <button
                onClick={() => {
                  setExpanded(false)
                  onOpenNutritionist('I want to log a meal. I\'ll describe what I ate.')
                }}
                className="flex items-center gap-3 px-4 py-2.5 bg-surface border border-border rounded-xl shadow-lg hover:bg-surface-high transition-all whitespace-nowrap"
              >
                <div className="w-8 h-8 bg-blue/10 rounded-lg flex items-center justify-center">
                  <MessageSquare size={16} className="text-blue" />
                </div>
                <span className="text-sm font-bold text-text">Text</span>
              </button>
            )}
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
    </>
  )
}
