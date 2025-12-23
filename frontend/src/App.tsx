import { useEffect, useState } from 'react'
import ChatInterface from './components/ChatInterface'
import HomePage from './components/HomePage'
import './App.css'

function getCanvasIdFromUrl() {
  try {
    const url = new URL(window.location.href)
    return url.searchParams.get('canvasId') || ''
  } catch {
    return ''
  }
}

function App() {
  const [canvasId, setCanvasId] = useState<string>(() => getCanvasIdFromUrl())

  useEffect(() => {
    const onPop = () => setCanvasId(getCanvasIdFromUrl())
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  return (
    <div className="app">
      {canvasId ? <ChatInterface initialCanvasId={canvasId} /> : <HomePage />}
    </div>
  )
}

export default App







