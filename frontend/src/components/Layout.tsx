import React from 'react'
import { CategoryPanel } from './CategoryPanel'
import { XMindViewer } from './XMindViewer'
import { ChatPanel } from './ChatPanel'

export const Layout: React.FC = () => {
  const [selectedPaper, setSelectedPaper] = React.useState<string | null>(null)
  const [chatOpen, setChatOpen] = React.useState(true)
  const [selectedNode, setSelectedNode] = React.useState<string | null>(null)

  return (
    <div className="flex h-screen bg-gray-50">
      <div className="w-64 bg-white border-r border-gray-200">
        <CategoryPanel onSelectPaper={setSelectedPaper} />
      </div>

      <div className="flex-1 bg-white">
        {selectedPaper ? (
          <XMindViewer
            paperId={selectedPaper}
            selectedNodeId={selectedNode}
            onNodeSelect={setSelectedNode}
          />
        ) : (
          <div className="flex items-center justify-center h-full text-gray-500">
            Select a paper to view its mind map
          </div>
        )}
      </div>

      {chatOpen && (
        <div className="w-96 bg-white border-l border-gray-200">
          <ChatPanel
            paperId={selectedPaper}
            onClose={() => setChatOpen(false)}
          />
        </div>
      )}

      {!chatOpen && (
        <button
          onClick={() => setChatOpen(true)}
          className="fixed right-4 bottom-4 bg-blue-500 text-white p-3 rounded-full shadow-lg hover:bg-blue-600"
        >
          Chat
        </button>
      )}
    </div>
  )
}
