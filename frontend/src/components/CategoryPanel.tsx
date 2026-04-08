import React, { useState, useEffect } from 'react'
import { Paper } from '../types'

interface CategoryPanelProps {
  onSelectPaper: (paperId: string) => void
}

export const CategoryPanel: React.FC<CategoryPanelProps> = ({ onSelectPaper }) => {
  const [papers, setPapers] = useState<Paper[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/papers')
      .then(res => res.json())
      .then(data => {
        setPapers(data.papers || [])
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  if (loading) {
    return <div className="p-4 text-gray-500">Loading papers...</div>
  }

  return (
    <div className="p-4">
      <h2 className="text-lg font-semibold mb-4">Papers</h2>
      
      {papers.length === 0 ? (
        <div className="text-gray-500 text-sm">No papers yet</div>
      ) : (
        <ul className="space-y-2">
          {papers.map(paper => (
            <li
              key={paper.paper_id}
              onClick={() => onSelectPaper(paper.paper_id)}
              className="p-2 rounded hover:bg-gray-100 cursor-pointer text-sm"
            >
              <div className="font-medium truncate">{paper.title}</div>
              <div className="text-xs text-gray-500">
                {new Date(paper.created_at).toLocaleDateString()}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
