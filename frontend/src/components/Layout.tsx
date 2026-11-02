import React from 'react'
import { CategoryPanel } from './CategoryPanel'
import { XMindViewer } from './XMindViewer'
import { ChatPanel } from './ChatPanel'

export const Layout: React.FC = () => {
  const [paper, setPaper] = React.useState<string | null>(null)
  const [node, setNode] = React.useState<string | null>(null)
  const [showChat, setShowChat] = React.useState(true)
  const selectPaper = (id: string) => { setPaper(id); setNode(null) }
  return <div className="flex h-screen bg-gray-50">
    <aside className="w-72 border-r bg-white overflow-auto">
      <CategoryPanel onSelectPaper={selectPaper} />
    </aside>
    <main className="flex-1 min-w-0 bg-white">
      {paper ? <XMindViewer paperId={paper} selectedNodeId={node} onNodeSelect={setNode} /> :
       <p className="p-6 text-gray-500">Upload or select a ready paper.</p>}
    </main>
    {showChat ? <aside className="w-96 border-l bg-white">
      <ChatPanel paperId={paper} selectedNodeId={node} onClose={() => setShowChat(false)} />
    </aside> : <button className="fixed right-4 bottom-4 bg-blue-500 text-white p-3 rounded"
      onClick={() => setShowChat(true)}>Chat</button>}
  </div>
}
