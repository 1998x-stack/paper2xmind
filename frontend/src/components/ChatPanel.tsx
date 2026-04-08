import React, { useState } from 'react'
import { ChatMessage } from '../types'

interface ChatPanelProps {
  paperId: string | null
  onClose: () => void
}

export const ChatPanel: React.FC<ChatPanelProps> = ({ paperId, onClose }) => {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')

  const handleSend = () => {
    if (!input.trim() || !paperId) return

    const userMessage: ChatMessage = {
      timestamp: new Date().toISOString(),
      role: 'user',
      content: input,
      message_id: `user_${Date.now()}`,
    }

    setMessages(prev => [...prev, userMessage])
    setInput('')

    setTimeout(() => {
      const assistantMessage: ChatMessage = {
        timestamp: new Date().toISOString(),
        role: 'assistant',
        content: 'Chat functionality will be implemented in Phase 2 with streaming.',
        message_id: `assistant_${Date.now()}`,
      }
      setMessages(prev => [...prev, assistantMessage])
    }, 500)
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  if (!paperId) {
    return <div className="p-4 text-gray-500">Select a paper to start chatting</div>
  }

  return (
    <div className="flex flex-col h-full">
      <div className="p-4 border-b border-gray-200 flex justify-between items-center">
        <h2 className="font-semibold">Chat</h2>
        <button onClick={onClose} className="text-gray-500 hover:text-gray-700">×</button>
      </div>

      <div className="flex-1 overflow-auto p-4 space-y-4">
        {messages.length === 0 ? (
          <div className="text-gray-500 text-sm">Ask questions about this paper...</div>
        ) : (
          messages.map(msg => (
            <div
              key={msg.message_id}
              className={`p-3 rounded-lg ${
                msg.role === 'user' ? 'bg-blue-100 ml-8' : 'bg-gray-100 mr-8'
              }`}
            >
              <div className="text-sm font-medium mb-1">{msg.role === 'user' ? 'You' : 'Assistant'}</div>
              <div className="text-sm">{msg.content}</div>
            </div>
          ))
        )}
      </div>

      <div className="p-4 border-t border-gray-200">
        <div className="flex space-x-2">
          <input
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Type your message..."
            className="flex-1 p-2 border border-gray-300 rounded-lg text-sm"
          />
          <button
            onClick={handleSend}
            className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 text-sm"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  )
}
