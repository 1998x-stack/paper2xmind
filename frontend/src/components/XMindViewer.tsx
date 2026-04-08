import React, { useState, useEffect } from 'react'
import { XMindData, XMindNode } from '../types'

interface XMindViewerProps {
  paperId: string
  selectedNodeId: string | null
  onNodeSelect: (nodeId: string) => void
}

export const XMindViewer: React.FC<XMindViewerProps> = ({
  paperId,
  selectedNodeId,
  onNodeSelect,
}) => {
  const [xmindData, setXMindData] = useState<XMindData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)

    fetch(`/api/papers/${paperId}/xmind`)
      .then(res => {
        if (!res.ok) throw new Error('Failed to load XMind data')
        return res.json()
      })
      .then(data => {
        setXMindData(data)
        setLoading(false)
      })
      .catch(err => {
        setError(err.message)
        setLoading(false)
      })
  }, [paperId])

  const renderNode = (node: XMindNode, level: number = 0) => {
    const isSelected = node.id === selectedNodeId
    const paddingLeft = level * 20

    return (
      <div key={node.id} style={{ paddingLeft }}>
        <div
          onClick={() => onNodeSelect(node.id)}
          className={`p-2 rounded cursor-pointer mb-1 ${
            isSelected ? 'bg-blue-100 border border-blue-300' : 'hover:bg-gray-100'
          }`}
        >
          <div className="font-medium">{node.title}</div>
          {node.notes && <div className="text-xs text-gray-600 mt-1">{node.notes}</div>}
        </div>
        
        {node.children && node.children.length > 0 && (
          <div className="ml-4 border-l border-gray-200">
            {node.children.map(child => renderNode(child, level + 1))}
          </div>
        )}
      </div>
    )
  }

  if (loading) {
    return <div className="flex items-center justify-center h-full text-gray-500">Loading mind map...</div>
  }

  if (error) {
    return <div className="flex items-center justify-center h-full text-red-500">Error: {error}</div>
  }

  if (!xmindData) {
    return <div className="flex items-center justify-center h-full text-gray-500">No XMind data</div>
  }

  return (
    <div className="h-full overflow-auto p-4">
      <h1 className="text-xl font-bold mb-4">{xmindData.xmind_data.title}</h1>
      <div className="space-y-2">
        {xmindData.xmind_data.children.map(node => renderNode(node))}
      </div>
    </div>
  )
}
