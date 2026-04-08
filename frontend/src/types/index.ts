export interface Paper {
  paper_id: string;
  title: string;
  created_at: string;
}

export interface XMindNode {
  id: string;
  title: string;
  children: XMindNode[];
  notes?: string;
  labels?: string[];
  collapsed?: boolean;
  selected?: boolean;
}

export interface XMindData {
  paper_id: string;
  xmind_data: {
    id: string;
    title: string;
    children: XMindNode[];
  };
}

export interface ChatMessage {
  timestamp: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  message_id: string;
  context?: {
    retrieved_paragraphs?: string[];
    xmind_nodes?: string[];
  };
}

export interface Category {
  name: string;
  paper_count: number;
  papers: Paper[];
}
