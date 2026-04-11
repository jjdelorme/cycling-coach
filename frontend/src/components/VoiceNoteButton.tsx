import { useState, useRef, useCallback } from 'react'
import { Mic, MicOff } from 'lucide-react'

interface Props {
  onRecorded: (blob: Blob, mimeType: string) => void
  maxDuration?: number // seconds, default 15
}

export default function VoiceNoteButton({ onRecorded, maxDuration = 15 }: Props) {
  const [recording, setRecording] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const chunksRef = useRef<Blob[]>([])

  const start = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      // Prefer webm; fall back to mp4 on iOS
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
        onRecorded(blob, mimeType.split(';')[0])
        setElapsed(0)
      }

      recorderRef.current = recorder
      recorder.start()
      setRecording(true)
      setElapsed(0)

      timerRef.current = setInterval(() => {
        setElapsed(prev => {
          if (prev + 1 >= maxDuration) {
            recorder.stop()
            setRecording(false)
            return 0
          }
          return prev + 1
        })
      }, 1000)
    } catch {
      // Microphone permission denied — silently ignore
    }
  }, [onRecorded, maxDuration])

  const stop = useCallback(() => {
    if (recorderRef.current && recorderRef.current.state === 'recording') {
      recorderRef.current.stop()
      setRecording(false)
    }
  }, [])

  return (
    <button
      onPointerDown={start}
      onPointerUp={stop}
      onPointerLeave={stop}
      className={`relative p-3 rounded-full transition-all ${
        recording
          ? 'bg-red text-white animate-pulse shadow-lg shadow-red/30'
          : 'bg-surface-low text-text-muted hover:text-accent hover:bg-accent/5'
      }`}
      title={recording ? `Recording... ${elapsed}s` : 'Hold to record voice note'}
    >
      {recording ? <MicOff size={20} /> : <Mic size={20} />}
      {recording && (
        <span className="absolute -top-1 -right-1 text-[9px] font-bold bg-red text-white rounded-full w-5 h-5 flex items-center justify-center">
          {elapsed}
        </span>
      )}
    </button>
  )
}
