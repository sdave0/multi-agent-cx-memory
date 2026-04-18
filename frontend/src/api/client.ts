export const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export interface User {
  id: string;
  role: 'customer' | 'agent' | 'admin';
  name?: string;
}

export interface ChatMessage {
  role: 'user' | 'ai' | 'tool' | 'system';
  content?: string;
  source?: string;
  timestamp?: number;
  latency?: number;
  name?: string;
  status?: string;
  result?: any;
  endTimestamp?: number;
}

export interface SessionQueueItem {
  session_id: string;
  tier: string;
  wait_time: string;
  title?: string;
  confidence?: number;
  reason?: string;
  takenOver?: boolean;
}

export interface TraceDecision {
  intent: string;
  specialist: string;
  context_note: string;
}

export interface SessionDetail {
  session_id: string;
  user_id: string;
  tier: string;
  outcome: string;
  specialist: string;
  resolved_entities: Record<string, string>;
  state_note: string;
  routing_decisions: TraceDecision[];
  message_history: ChatMessage[];
}

export class APIClient {
  static getHeaders(): Record<string, string> {
    const token = localStorage.getItem('mindcx_token');
    return {
      'Content-Type': 'application/json',
      ...(token ? { 'Authorization': `Bearer ${token}` } : {})
    };
  }

  static async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = `${BASE_URL}${endpoint}`;
    const headers = { ...this.getHeaders(), ...options.headers };
    
    const response = await fetch(url, { ...options, headers });
    
    if (response.status === 401 || response.status === 403) {
        // Intercept 401/403 and reload to clear state and push to /login
        localStorage.removeItem('mindcx_token');
        localStorage.removeItem('mindcx_user');
        window.location.reload();
        throw new Error('Unauthorized');
    }
    
    if (!response.ok) {
        throw new Error(`API Error: ${response.statusText}`);
    }

    // Some endpoints may not return JSON, handle accordingly if needed, 
    // but default to parsing JSON.
    return response.json() as Promise<T>;
  }

  static async getQueue(): Promise<{ queue: SessionQueueItem[] }> {
    return this.request<{ queue: SessionQueueItem[] }>('/api/escalation/queue');
  }

  static async takeoverSession(sessionId: string, agentId: string): Promise<any> {
    return this.request('/api/escalation/takeover', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId, agent_id: agentId })
    });
  }

  static async sendAgentMessage(sessionId: string, text: string, agentId: string): Promise<any> {
    return this.request(`/api/escalation/agent-message/${sessionId}`, {
      method: 'POST',
      body: JSON.stringify({ text, agent_id: agentId })
    });
  }

  static async getSessions(): Promise<{ sessions: SessionDetail[] }> {
    return this.request<{ sessions: SessionDetail[] }>('/api/escalation/sessions');
  }

  static async getSessionDetail(sessionId: string): Promise<SessionDetail> {
    return this.request<SessionDetail>(`/api/escalation/session/${sessionId}`);
  }
}
