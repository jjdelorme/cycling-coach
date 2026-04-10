import { useRef, useState } from 'react'
import { Camera, Loader2 } from 'lucide-react'
import { useLogMeal } from '../hooks/useApi'
import MacroAnalysisCard from './MacroAnalysisCard'
import VoiceNoteButton from './VoiceNoteButton'
import type { MealDetail } from '../types/api'

interface Props {
  onMealSaved?: (meal: MealDetail) => void
}

export default function MealCapture({ onMealSaved }: Props) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [audioBlob, setAudioBlob] = useState<{ blob: Blob; mime: string } | null>(null)
  const logMeal = useLogMeal()

  const handleCapture = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    // Show preview immediately
    setPreview(URL.createObjectURL(file))

    try {
      const result = await logMeal.mutateAsync({
        file,
        audio: audioBlob?.blob,
        audioMimeType: audioBlob?.mime,
      })
      onMealSaved?.(result)
      // Clear on success only — on error we keep preview so MacroAnalysisCard
      // stays visible and can display the error message to the user.
      setPreview(null)
      setAudioBlob(null)
    } catch {
      // preview stays set → card remains mounted → error prop is shown
    } finally {
      // Always reset the file input so the same photo can be re-selected
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  return (
    <>
      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        capture="environment"
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

      {/* Voice note + FAB stack */}
      <div className="fixed bottom-24 right-6 md:bottom-8 md:right-8 flex flex-col items-center gap-2 z-30">
        <div className="relative">
          <VoiceNoteButton
            onRecorded={(blob, mime) => setAudioBlob({ blob, mime })}
          />
          {audioBlob && (
            <span className="absolute -top-1 -right-1 w-2 h-2 bg-green rounded-full" />
          )}
        </div>

        {/* FAB */}
        <button
          onClick={() => fileRef.current?.click()}
          disabled={logMeal.isPending}
          className="w-14 h-14 bg-accent text-white rounded-full shadow-lg shadow-accent/20 flex items-center justify-center hover:opacity-90 active:scale-95 transition-all disabled:opacity-50"
          title="Log a meal"
        >
          {logMeal.isPending ? (
            <Loader2 size={24} className="animate-spin" />
          ) : (
            <Camera size={24} />
          )}
        </button>
      </div>
    </>
  )
}
