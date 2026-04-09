import React, { useState, useEffect, useRef } from 'react'
import { ChatMessage } from '../types'

interface ChatPanelProps {
  paperId: string | null
  onClose: () => void
}

export const ChatPanel: React.FC<ChatPanelProps> = ({ paperId, onClose }) => {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  useEffect(() => {
    if (paperId) {
      // Load chat history
      fetch(`/api/papers/${paperId}/chat`)
        .then(res => res.json())
        .then(data => {
          if (data.messages && data.messages.length > 0) {
            setMessages(data.messages)
          }
        })
        .catch(console.error)
    }
  }, [paperId])

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
    setIsStreaming(true)

    // Start SSE stream
    fetch(`/api/papers/${paperId}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: input, message_id: userMessage.message_id }),
    })
      .then(response => {
        if (!response.ok) throw new Error('Stream failed')
        const reader = response.body?.getReader()
        if (!reader) throw new Error('No reader')

        const decoder = new TextDecoder()
        let assistantContent = ''
        let messageId = ''

        const read = () => {
          reader.read().then(({ done, value }) => {
            if (done) {
              setIsStreaming(false)
              return
            }

            const chunk = decoder.decode(value)
            const lines = chunk.split('\n\n')

            for (const line of lines) {
              if (line.startsWith('data: ')) {
                try {
                  const data = JSON.parse(line.slice(6))

                  if (data.type === 'chunk') {
                    assistantContent += data.content
                    messageId = data.message_id

                    setMessages(prev => {
                      const lastMsg = prev[prev.length - 1]
                      if (lastMsg?.role === 'assistant' && lastMsg.message_id === messageId) {
                        return [...prev.slice(0, -1), { ...lastMsg, content: assistantContent }]
                      }
                      return [...prev, {
                        timestamp: new Date().toISOString(),
                        role: 'assistant',
                        content: assistantContent,
                        message_id: messageId,
                      }]
                    })
                  } else if (data.type === 'error') {
                    console.error('Stream error:', data.message)
                    setIsStreaming(false)
                  }
                } catch (e) {
                  // Ignore parse errors for incomplete chunks
                }
              }
            }

            read()
          })
        }

        read()
      })
      .catch(err => {
        console.error('Chat stream error:', err)
        setIsStreaming(false)
        // Add error message
        setMessages(prev => [...prev, {
          timestamp: new Date().toISOString(),
          role: 'assistant',
          content: 'Error: Could not connect to chat service. Please check if the backend is running.',
          message_id: `error_${Date.now()}`,
        }])
      })
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
        <div ref={messagesEndRef} />
      </div>

      <div className="p-4 border-t border-gray-200">
        <div className="flex space-x-2">
          <input
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder={isStreaming ? 'Waiting for response...' : 'Type your message...'}
            disabled={isStreaming}
            className="flex-1 p-2 border border-gray-300 rounded-lg text-sm disabled:bg-gray-100"
          />
          <button
            onClick={handleSend}
            disabled={isStreaming || !input.trim()}
            className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 text-sm disabled:bg-gray-400"
          >
            {isStreaming ? '...' : 'Send'}
          </button>
        </div>
      </div>
    </div>
  )
}
