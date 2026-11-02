export interface Paper {
  paper_id:string; title:string; created_at:string; status:string; job_id?:string
}
export interface XMindNode {
  id:string; title:string; children:XMindNode[]; notes_text?:string; labels?:string[]
}
export interface XMindData {paper_id:string; xmind_data:XMindNode}
export interface ChatMessage {
  timestamp:string; role:'user'|'assistant'|'system'; content:string; message_id:string
  context?: {retrieved_paragraphs?:string[];xmind_nodes?:string[]}
}
export interface Category {name:string;paper_count:number;papers:Paper[]}
