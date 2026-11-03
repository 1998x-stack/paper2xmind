/** Parse SSE with carry-over buffer across arbitrary network chunk boundaries. */
export function parseSSEFrames(pending: string, incoming: string): {
  pending: string; frames: string[]
} {
  const combined = (pending + incoming).replace(/\r\n/g, '\n')
  const segments = combined.split('\n\n')
  return {pending: segments.pop() || '', frames: segments}
}
export function parseSSEData(frame: string): unknown | null {
  const content = frame.split('\n').filter(s => s.startsWith('data:'))
    .map(s => s.slice(5).trimStart()).join('\n')
  if (!content) return null
  try { return JSON.parse(content) } catch { return null }
}
