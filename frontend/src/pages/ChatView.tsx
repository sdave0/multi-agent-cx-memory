import React, { useState, useEffect, useRef } from 'react';
import { Send, Cpu, Link, AlertTriangle, Download } from 'lucide-react';
import { SidebarContext } from '../components/Sidebar';
import { ChatMessage } from '../api/client';

interface ChatViewProps {
  onContextUpdate?: (context: SidebarContext) => void;
}

export default function ChatView({ onContextUpdate }: ChatViewProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<'ai' | 'human'>('ai');
  const [currentTools, setCurrentTools] = useState<string[]>([]);
  
  const ws = useRef<WebSocket | null>(null);
  const sessionId = useRef("sess_" + Math.random().toString(36).substring(2, 15));
  const lastUserMsgTime = useRef<number | null>(null);
  const contextState = useRef<SidebarContext>({ tier: 'PRO' });

  const updateContext = (update: Partial<SidebarContext>) => {
    contextState.current = { ...contextState.current, ...update };
    onContextUpdate?.(contextState.current);
  };

  useEffect(() => {
    // Session ID is persistent for this mount
    const currentSessionId = sessionId.current;
    const token = localStorage.getItem('mindcx_token');

    if (!token) {
      setError("Not authenticated. Please log in.");
      return;
    }
    
    // Connect to Backend WebSocket with Token
    try {
      ws.current = new WebSocket(`ws://localhost:8000/ws/${currentSessionId}?token=${token}`);
      
      ws.current.onopen = () => {
        setConnected(true);
        setError(null);
      };

      ws.current.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'error') {
            setError(data.message);
            return;
        }
        if (data.type === 'token') {
            const agent = data.agent || 'CONCIERGE';
            const node = agent.toLowerCase().replace(' ', '_');
            
            updateContext({ lastNode: node });

            setMessages(prev => {
                const newMsgs = [...prev];
                const lastIndex = newMsgs.length - 1;
                const last = newMsgs[lastIndex];
                if (last && last.role === 'ai' && last.source === agent) {
                    newMsgs[lastIndex] = { ...last, content: last.content + data.data };
                } else {
                    const latency = lastUserMsgTime.current ? Date.now() - lastUserMsgTime.current : undefined;
                    newMsgs.push({ role: 'ai', content: data.data, source: agent, timestamp: Date.now(), latency });
                }
                return newMsgs;
            });
        } else if (data.type === 'tool_start') {
            const toolName = data.tool;
            const newTools = [...(contextState.current.tools || []), toolName];
            updateContext({ tools: newTools });
            
            const latency = lastUserMsgTime.current ? Date.now() - lastUserMsgTime.current : undefined;
            setMessages(prev => [...prev, { role: 'tool', name: toolName, status: 'Running...', timestamp: Date.now(), latency }]);
        } else if (data.type === 'routing_decision') {
            const info = data.info || '';
            const updates: Partial<SidebarContext> = {};
            
            if (info.includes('Intent identified:')) {
                updates.intent = info.split('Intent identified:')[1].trim();
                updates.lastNode = 'concierge';
            }
            if (info.includes('Quality Lead Audit:')) {
                updates.lastNode = 'quality_lead';
            }
            
            updateContext(updates);
        } else if (data.type === 'session_info') {
            updateContext({
                tier: data.tier,
                user_id: data.user_id
            });
        } else if (data.type === 'tool_end') {
            setMessages(prev => {
                const newMsgs = [...prev];
                const lastIndex = newMsgs.map(m => m.role).lastIndexOf('tool');
                if (lastIndex !== -1) {
                    newMsgs[lastIndex].status = 'Success';
                    newMsgs[lastIndex].result = data.result;
                    newMsgs[lastIndex].endTimestamp = Date.now();
                }
                return newMsgs;
            });
        } else if (data.type === 'human_takeover') {
            setMode('human');
            setMessages(prev => [...prev, { role: 'system', content: 'A human agent has taken over the chat. AI paused.', source: 'SYSTEM', timestamp: Date.now() }]);
        } else if (data.type === 'escalation') {
            setMessages(prev => [...prev, { role: 'system', content: `Transferring you to a human agent. Reason: ${data.reason} (Ticket: ${data.ticket})`, source: 'SYSTEM', timestamp: Date.now() }]);
        } else if (data.type === 'retry_clear') {
            // The Quality Lead issued a RETRY — remove the specialist's last (failed)
            // message bubble so the user sees a clean replacement when the specialist
            // re-runs, rather than stacked or repeated messages.
            const agentSource = data.agent || '';
            setMessages(prev => {
                const lastAiIdx = [...prev].map((m, i) => ({ m, i }))
                    .filter(({ m }) => m.role === 'ai' && m.source === agentSource)
                    .map(({ i }) => i)
                    .pop();
                if (lastAiIdx !== undefined) {
                    const newMsgs = [...prev];
                    newMsgs.splice(lastAiIdx, 1);
                    return newMsgs;
                }
                return prev;
            });
        }
      };

      ws.current.onclose = () => {
        setConnected(false);
        setError("WebSocket Connection Lost. Reload to reconnect.");
      };
      
      ws.current.onerror = (e) => {
          console.error("WS Error", e);
          setError("WebSocket failed to connect to ws://localhost:8000.");
      };

    } catch (e) {
      setError(String(e));
    }

    return () => {
      ws.current?.close();
    };
  }, []);

  const sendMessage = () => {
    if (!input.trim() || !ws.current) return;
    lastUserMsgTime.current = Date.now();
    setMessages(prev => [...prev, { role: 'user', content: input, timestamp: Date.now() }]);
    ws.current.send(JSON.stringify({ text: input }));
    setInput('');
  };

  const exportChatAsMarkdown = () => {
    let md = `# Nexus Chat Trace: ${sessionId.current}\n`;
    md += `- **Date**: ${new Date().toLocaleString()}\n`;
    md += `- **Status**: ${connected ? 'LIVE' : 'DISCONNECTED'}\n`;
    md += `- **Mode**: ${mode.toUpperCase()}\n\n`;
    md += `--- \n\n## Chat Timeline\n\n`;

    messages.forEach((msg, idx) => {
      const timeStr = msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString() : 'N/A';
      const latencyStr = msg.latency ? ` (Latency: ${(msg.latency / 1000).toFixed(2)}s)` : '';

      if (msg.role === 'user') {
        md += `### 👤 User [${timeStr}]\n${msg.content}\n\n`;
      } else if (msg.role === 'ai') {
        md += `### 🤖 ${msg.source} [${timeStr}]${latencyStr}\n${msg.content}\n\n`;
      } else if (msg.role === 'tool') {
        md += `### ⚙️ Tool Execution: ${msg.name} [${timeStr}]${latencyStr}\n`;
        md += `- **Status**: ${msg.status}\n`;
        if (msg.result) {
          md += `- **Result**:\n\`\`\`json\n${typeof msg.result === 'object' ? JSON.stringify(msg.result, null, 2) : msg.result}\n\`\`\`\n`;
        }
        md += `\n`;
      } else if (msg.role === 'system') {
        md += `> **SYSTEM**: ${msg.content} [${timeStr}]\n\n`;
      }
    });

    const blob = new Blob([md], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `mindcx_trace_${sessionId.current}_${Date.now()}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div style={{ display: 'flex', height: '100%' }}>
      <div style={{ flex: 1, padding: '2rem 4rem', display: 'flex', flexDirection: 'column', position: 'relative' }}>
        
        {error && (
            <div style={{ backgroundColor: '#FEF2F2', padding: '1rem', color: '#991B1B', borderRadius: 'var(--radius-md)', display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
                <AlertTriangle size={16} /> Server Connection Error: {error}
            </div>
        )}

        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '3rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <div style={{ width: '40px', height: '40px', borderRadius: '50%', backgroundColor: connected ? '#D1FAE5' : '#FEE2E2', display: 'flex', alignItems: 'center', justifyContent: 'center', color: connected ? 'var(--primary)' : '#991B1B' }}>
              <Cpu size={24} />
            </div>
            <div>
              <h2 className="display" style={{ fontSize: '1.25rem', margin: 0 }}>Active Support Cluster</h2>
              <div style={{ fontSize: '0.85rem', color: 'var(--on-surface-variant)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <div style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: connected ? 'var(--primary)' : '#991B1B' }} />
                {connected ? (mode === 'ai' ? 'Concierge + Speciallist Engaged' : 'Human Agent Connected') : 'System Offline'}
              </div>
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem', flex: 1, overflowY: 'auto', paddingBottom: '100px' }}>
          
          {messages.length === 0 && <div style={{ textAlign: 'center', color: 'var(--on-surface-variant)', marginTop: '4rem' }}>Type a message below to instantiate the active tracing sequence...</div>}

          {messages.map((msg, i) => (
            <React.Fragment key={i}>
                {msg.role === 'user' && (
                  <div style={{ alignSelf: 'flex-end', maxWidth: '70%' }}>
                    <div className="label" style={{ textAlign: 'right', marginBottom: '0.5rem' }}>Client</div>
                    <div style={{ backgroundColor: '#F0F4FF', padding: '1.25rem', borderRadius: '1rem', borderTopRightRadius: '2px', color: 'var(--on-surface)' }}>
                      {msg.content}
                    </div>
                  </div>
                )}
                {msg.role === 'ai' && (
                  <div style={{ alignSelf: 'flex-start', maxWidth: '80%' }}>
                    <div className="label" style={{ marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--primary)' }}>
                      <Cpu size={14} /> {msg.source}
                    </div>
                    <div style={{ backgroundColor: 'var(--surface-low)', padding: '1.25rem', borderRadius: '1rem', borderTopLeftRadius: '2px' }}>
                      {msg.content}
                    </div>
                  </div>
                )}
                {msg.role === 'system' && (
                  <div style={{ alignSelf: 'center', margin: '1rem 0', color: 'var(--primary)', fontWeight: 'bold', fontSize: '0.85rem' }}>
                    --- {msg.content} ---
                  </div>
                )}
                {msg.role === 'tool' && (
                  <div style={{ alignSelf: 'flex-start', width: '80%', paddingLeft: '2rem' }}>
                     <div style={{ border: 'var(--border-ghost)', borderRadius: 'var(--radius-md)', overflow: 'hidden' }}>
                       <div style={{ backgroundColor: '#FAFAFA', padding: '0.75rem 1rem', borderBottom: 'var(--border-ghost)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                         <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--on-surface-variant)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            <Link size={12} /> EXECUTION: {msg.name}
                         </div>
                         <div style={{ fontSize: '0.75rem', color: msg.status === 'Success' ? 'var(--primary)' : '#B45309', fontWeight: 600 }}>{msg.status}</div>
                       </div>
                       {msg.result && (
                           <div style={{ padding: '1rem', backgroundColor: 'var(--surface-lowest)', fontFamily: 'monospace', fontSize: '0.8rem', color: 'var(--on-surface-variant)', whiteSpace: 'pre-wrap' }}>
                            {typeof msg.result === 'object' ? JSON.stringify(msg.result, null, 2) : msg.result}
                           </div>
                       )}
                     </div>
                  </div>
                )}
            </React.Fragment>
          ))}
        </div>

        <div style={{ position: 'absolute', bottom: '2rem', left: '4rem', right: '4rem' }}>
          <div className="glass-panel" style={{ display: 'flex', padding: '0.5rem', borderRadius: '1rem', backgroundColor: 'var(--surface-low)', alignItems: 'center' }}>
             <div style={{ padding: '0 1rem', color: 'var(--on-surface-variant)' }}>
               <Link size={20} />
             </div>
             <input 
               type="text" 
               value={input}
               onChange={e => setInput(e.target.value)}
               onKeyDown={e => e.key === 'Enter' && sendMessage()}
               placeholder={mode === 'ai' ? "Type your follow-up here..." : "Chatting with human agent..."}
               style={{ flex: 1, backgroundColor: 'transparent', border: 'none', outline: 'none', padding: '0.75rem 0', fontSize: '1rem', color: 'var(--on-surface)' }}
             />
             <button onClick={sendMessage} style={{ backgroundColor: 'var(--primary)', color: 'white', borderRadius: '50%', width: '48px', height: '48px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
               <Send size={20} />
             </button>
          </div>
        </div>

      </div>

      <div style={{ width: '300px', backgroundColor: 'var(--surface-lowest)', borderLeft: '1px solid var(--surface-low)', padding: '2rem' }}>
        <h3 className="label" style={{ marginBottom: '2rem' }}>Live Observability</h3>
        
        <div style={{ backgroundColor: 'var(--base-bg)', padding: '1rem', borderRadius: 'var(--radius-sm)', marginBottom: '1rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', fontWeight: 600, marginBottom: '0.5rem' }}>
            <span>CONNECTION</span>
            <span style={{ color: connected ? 'var(--primary)' : '#991B1B' }}>{connected ? 'LIVE' : 'OFFLINE'}</span>
          </div>
          <div style={{ height: '4px', backgroundColor: '#E2E8F0', borderRadius: '4px', overflow: 'hidden' }}>
            <div style={{ height: '100%', width: connected ? '100%' : '5%', backgroundColor: connected ? 'var(--primary)' : '#991B1B' }} />
          </div>
        </div>

        <h4 className="label" style={{ fontSize: '0.7rem', marginBottom: '1rem' }}>MODEL DETAILS</h4>
        <div style={{ fontSize: '0.8rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          {/* Add back model details if needed, but keeping it clean for now as requested */}
        </div>
        
        <button 
          onClick={exportChatAsMarkdown}
          className="btn-primary" 
          style={{ width: '100%', marginTop: '2rem', padding: '0.6rem', fontSize: '0.85rem' }}
        >
          <Download size={16} /> Download Chat Trace
        </button>
      </div>
    </div>
  );
}
