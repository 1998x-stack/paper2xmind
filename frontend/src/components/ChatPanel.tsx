import React, {useEffect,useRef,useState} from 'react'
import type {ChatMessage} from '../types'
import {parseSSEFrames,parseSSEData} from '../utils/sse'

interface Props {paperId:string|null;selectedNodeId:string|null;onClose:()=>void}
export const ChatPanel: React.FC<Props> = ({paperId,selectedNodeId,onClose}) => {
  const [messages,setMessages] = useState<ChatMessage[]>([])
  const [input,setInput] = useState('')
  const [busy,setBusy] = useState(false)
  const [error,setError] = useState('')
  const abortRef = useRef<AbortController|null>(null)
  const bottom = useRef<HTMLDivElement>(null)
  useEffect(() => {bottom.current?.scrollIntoView({behavior:'smooth'})},[messages])
  useEffect(() => {
    abortRef.current?.abort();setMessages([]);setError('');setBusy(false)
    if (!paperId) return
    const controller = new AbortController()
    fetch('/api/papers/' + paperId + '/chat',{signal:controller.signal})
      .then(r => r.json()).then(d => {if (!controller.signal.aborted) setMessages(d.messages||[])})
      .catch(e => {if (!controller.signal.aborted) setError(String(e))})
    return () => {controller.abort();abortRef.current?.abort()}
  },[paperId])
  const send = async () => {
    if (!paperId || !input.trim() || busy) return
    const question = input.trim()
    const user:ChatMessage = {timestamp:new Date().toISOString(),role:'user',
      content:question,message_id:'user_'+Date.now()}
    setMessages(p => [...p,user]);setInput('');setError('');setBusy(true)
    const controller = new AbortController()
    abortRef.current = controller
    try {
      const res = await fetch('/api/papers/' + paperId + '/chat/stream',{
        method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json'},
        body:JSON.stringify({message:question,message_id:user.message_id,
          selected_nodes:selectedNodeId?[selectedNodeId]:[]})
      })
      if (!res.ok || !res.body) throw Error('Chat HTTP '+res.status)
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let pending = '', answer = ''
      while (true) {
        const {done,value} = await reader.read()
        const chunk = decoder.decode(value,{stream:!done})
        const result = parseSSEFrames(pending,chunk)
        pending = result.pending
        for (const frame of result.frames) {
          const event = parseSSEData(frame) as
            {type:string,content?:string,message?:string,message_id?:string}|null
          if (!event) continue
          if (event.type === 'error') throw Error(event.message || 'Chat failed')
          if (event.type === 'chunk') {
            answer += event.content || ''
            const id = event.message_id || 'assistant'
            setMessages(prev => {
              const reply:ChatMessage = {timestamp:new Date().toISOString(),
                role:'assistant',content:answer,message_id:id}
              const found = prev.findIndex(m => m.message_id === id)
              return found < 0 ? [...prev,reply] : prev.map((m,i)=> i===found ? reply : m)
            })
          }
        }
        if (done) break
      }
    } catch(e) {if (!controller.signal.aborted) setError(String(e))}
    finally {if (abortRef.current === controller) abortRef.current = null
      if (!controller.signal.aborted) setBusy(false)}
  }
  if (!paperId) return <div className="p-4">Select a ready paper to chat</div>
  return <div className="flex flex-col h-full">
    <header className="p-4 border-b flex justify-between">
      <h2 className="font-semibold">Chat</h2>
      <button onClick={onClose} aria-label="Close chat">×</button>
    </header>
    {selectedNodeId && <p className="text-xs text-gray-500 p-2">Selected node: {selectedNodeId}</p>}
    <div className="flex-1 overflow-auto p-3 space-y-2">
      {messages.map(msg => <div key={msg.message_id}
        className={'p-2 rounded text-sm '+(msg.role==='user'?'bg-blue-100':'bg-gray-100')}>
        <b className="block">{msg.role==='user'?'You':'Assistant'}</b>
        <span className="whitespace-pre-wrap">{msg.content}</span>
      </div>)}
      {error && <p role="alert" className="text-red-600 text-xs">{error}</p>}
      <div ref={bottom}/>
    </div>
    <form className="p-3 flex gap-2" onSubmit={e => {e.preventDefault();void send()}}>
      <input className="border p-2 rounded flex-1 min-w-0 text-sm" value={input}
        onChange={e=>setInput(e.target.value)} disabled={busy} placeholder="Ask about the paper"/>
      <button type="submit" disabled={busy||!input.trim()}
        className="bg-blue-600 text-white p-2 rounded disabled:opacity-50">Send</button>
    </form>
  </div>
}
