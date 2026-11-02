import React, { useEffect, useState } from 'react'
import type { Paper } from '../types'

export const CategoryPanel: React.FC<{onSelectPaper: (id: string) => void}> = ({onSelectPaper}) => {
  const [papers, setPapers] = useState<Paper[]>([])
  const [error, setError] = useState('')
  const [uploading, setUploading] = useState(false)
  useEffect(() => {
    let active = true
    const refresh = async () => {
      try {
        const response = await fetch('/api/papers')
        if (!response.ok) throw Error('Cannot load paper library')
        const data = await response.json()
        if (active) setPapers(data.papers || [])
      } catch (err) { if (active) setError(String(err)) }
    }
    void refresh()
    const id = setInterval(() => void refresh(), 2000)
    return () => { active = false; clearInterval(id) }
  }, [])
  const upload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    setUploading(true); setError('')
    try {
      const data = new FormData()
      data.append('file', file)
      const response = await fetch('/api/papers/upload', {method:'POST', body:data})
      if (!response.ok) {
        const problem = await response.json()
        throw Error(problem.detail || 'Upload rejected')
      }
      const list = await fetch('/api/papers')
      if (list.ok) setPapers((await list.json()).papers || [])
    } catch (err) { setError(String(err)) }
    finally { setUploading(false); event.target.value = '' }
  }
  return <div className="p-4">
    <h2 className="font-semibold mb-3">Paper Library</h2>
    <label className="block text-xs mb-4">Upload PDF
      <input className="block mt-1 w-full" type="file" accept=".pdf,application/pdf"
        disabled={uploading} onChange={upload}/>
    </label>
    {uploading && <p role="status">Uploading...</p>}
    {error && <p className="text-red-600 text-xs" role="alert">{error}</p>}
    {papers.length === 0 && <p className="text-sm text-gray-500">No papers yet</p>}
    <ul className="space-y-2">
      {papers.map(paper => <li key={paper.paper_id}>
        <button type="button" className="text-left p-2 w-full rounded hover:bg-gray-100 disabled:opacity-50"
          disabled={paper.status !== 'READY'} onClick={() => onSelectPaper(paper.paper_id)}>
          <span className="block text-sm font-medium break-words">{paper.title}</span>
          <span className="text-xs text-gray-500">{paper.status.toLowerCase().replace(/_/g, ' ')}</span>
        </button>
      </li>)}
    </ul>
  </div>
}
