import React, { useEffect, useState } from 'react'
import type { XMindData, XMindNode } from '../types'

interface Props {paperId: string; selectedNodeId: string | null; onNodeSelect: (id: string) => void}

export const XMindViewer: React.FC<Props> = ({paperId,selectedNodeId,onNodeSelect}) => {
  const [data,setData] = useState<XMindData | null>(null)
  const [error,setError] = useState('')
  const [loading,setLoading] = useState(true)
  useEffect(() => {
    const controller = new AbortController()
    setData(null); setError(''); setLoading(true)
    fetch('/api/papers/' + paperId + '/mindmap', {signal:controller.signal})
      .then(res => {if (!res.ok) throw Error('Mind map unavailable'); return res.json()})
      .then(body => setData(body))
      .catch(err => {if (!controller.signal.aborted) setError(String(err))})
      .finally(() => {if (!controller.signal.aborted) setLoading(false)})
    return () => controller.abort()
  }, [paperId])
  const nodeView = (node: XMindNode, depth = 0): React.ReactNode =>
    <div key={node.id} style={{paddingLeft:depth * 16}}>
      <button type="button" onClick={() => onNodeSelect(node.id)}
        className={'w-full text-left rounded p-2 mb-1 ' +
          (selectedNodeId === node.id ? 'bg-blue-100 border border-blue-300' : 'hover:bg-gray-100')}>
        <span className="block font-medium">{node.title}</span>
        {node.notes_text && <span className="block text-xs text-gray-600 whitespace-pre-wrap">{node.notes_text}</span>}
      </button>
      {node.children?.map(child => nodeView(child,depth + 1))}
    </div>
  if (loading) return <p className="p-5">Loading mind map...</p>
  if (error) return <p className="p-5 text-red-600" role="alert">{error}</p>
  if (!data) return <p className="p-5">No mind map</p>
  return <div className="h-full overflow-auto p-4">
    <div className="flex items-center justify-between gap-4 mb-4">
      <h1 className="text-lg font-semibold">{data.xmind_data.title}</h1>
      <a className="text-blue-600 underline text-sm flex-shrink-0"
        href={'/api/papers/' + paperId + '/artifacts/xmind'}>Download XMind</a>
    </div>
    {nodeView(data.xmind_data)}
  </div>
}
