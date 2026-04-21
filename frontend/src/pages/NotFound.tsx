import { Link } from 'react-router-dom'
import { Compass } from 'lucide-react'

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <Compass size={64} className="text-text-muted opacity-20 mb-6" />
      <h1 className="text-3xl font-bold text-text mb-2">Page not found</h1>
      <p className="text-text-muted text-sm mb-8 max-w-md">
        The page you're looking for doesn't exist or may have been moved.
      </p>
      <Link
        to="/"
        className="px-4 py-2 bg-accent text-white rounded-lg text-sm font-bold uppercase tracking-widest hover:opacity-90 transition-opacity"
      >
        Go to Dashboard
      </Link>
    </div>
  )
}
