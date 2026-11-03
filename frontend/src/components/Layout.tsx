import React from 'react'
import { CategoryPanel } from './CategoryPanel'
import { XMindViewer } from './XMindViewer'
import { ChatPanel } from './ChatPanel'
import { EvidencePanel } from './EvidencePanel'

export const Layout: React.FC = () => {
  const [paper, setPaper] = React.useState<string | null>(null)
  const [node, setNode] = React.useState<string | null>(null)
  const [showChat, setShowChat] = React.useState(true)
  const [workspace, setWorkspace] = React.useState<'mindmap' | 'evidence'>('mindmap')
  const selectPaper = (id: string) => { setPaper(id); setNode(null) }
  return <div className="flex h-screen bg-gray-50">
    <aside className="w-72 border-r bg-white overflow-auto">
      <CategoryPanel onSelectPaper={selectPaper} />
    </aside>
    <main className="flex-1 min-w-0 bg-white flex flex-col">
      <nav className="flex border-b gap-2 p-2" aria-label="Paper workspaces">
        <a href="/demo" className="rounded px-3 py-2 text-sm font-medium text-indigo-700 hover:bg-indigo-50">Public demo</a>
        <button type="button" aria-pressed={workspace === 'mindmap'}
          className={'rounded px-3 py-2 text-sm ' + (workspace === 'mindmap' ? 'bg-blue-100 font-medium' : 'hover:bg-gray-100')}
          onClick={() => setWorkspace('mindmap')}>Mind map</button>
        <button type="button" aria-pressed={workspace === 'evidence'}
          className={'rounded px-3 py-2 text-sm ' + (workspace === 'evidence' ? 'bg-blue-100 font-medium' : 'hover:bg-gray-100')}
          onClick={() => setWorkspace('evidence')}>Evidence inspector</button>
      </nav>
      <div className="flex-1 min-h-0">
        {paper ? (workspace === 'evidence'
          ? <EvidencePanel paperId={paper} />
          : <XMindViewer paperId={paper} selectedNodeId={node} onNodeSelect={setNode} />) :
         <p className="p-6 text-gray-500">Upload or select a ready paper.</p>}
      </div>
    </main>
    {showChat ? <aside className="w-96 border-l bg-white">
      <ChatPanel paperId={paper} selectedNodeId={node} onClose={() => setShowChat(false)} />
    </aside> : <button className="fixed right-4 bottom-4 bg-blue-500 text-white p-3 rounded"
      onClick={() => setShowChat(true)}>Chat</button>}
  </div>
}
