import React, { useState, useEffect } from 'react';
import { ShieldAlert, Activity, Users, Send } from 'lucide-react';
import { APIClient, SessionQueueItem } from '../api/client';

export default function EscalationDashboard() {
  const [queue, setQueue] = useState<SessionQueueItem[]>([]);
  const [activeItem, setActiveItem] = useState<SessionQueueItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState('');
  const [sending, setSending] = useState(false);

  useEffect(() => {
    const fetchQueue = async () => {
      try {
        const data = await APIClient.getQueue();
        setQueue(data.queue || []);
        
        // Auto-select first item if none active
        if (data.queue && data.queue.length > 0 && !activeItem) {
           setActiveItem(data.queue[0]);
        }
        setError(null);
      } catch (e: unknown) {
        if (e instanceof Error) {
            setError(e.message);
        } else {
            setError(String(e));
        }
      } finally {
        setLoading(false);
      }
    };

    fetchQueue();
    const interval = setInterval(fetchQueue, 5000);
    return () => clearInterval(interval);
  }, [activeItem]);

  const handleTakeover = async () => {
    if (!activeItem) return;
    try {
      await APIClient.takeoverSession(activeItem.session_id, 'human_agent_1');
      setQueue(queue.filter(item => item.session_id !== activeItem.session_id));
      setActiveItem({ ...activeItem, takenOver: true });
    } catch (e) {
      console.error(e);
    }
  };

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeItem || !activeItem.takenOver || !message.trim()) return;

    setSending(true);
    try {
      await APIClient.sendAgentMessage(activeItem.session_id, message, 'human_agent_1');
      setMessage('');
    } catch (e) {
      console.error(e);
    } finally {
      setSending(false);
    }
  };

  return (
    <div style={{ display: 'flex', height: '100%' }}>
      {/* Escalation Queue (Left Panel) */}
      <div style={{ width: '340px', backgroundColor: 'var(--surface-lowest)', borderRight: '1px solid var(--surface-low)', display: 'flex', flexDirection: 'column' }}>
        
        <div style={{ padding: '2rem 1.5rem', display: 'flex', gap: '1rem' }}>
          <div style={{ flex: 1, backgroundColor: 'var(--base-bg)', padding: '1rem', borderRadius: 'var(--radius-md)', textAlign: 'center' }}>
            <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--on-surface-variant)' }}>SYSTEM LOAD</div>
            <div style={{ fontSize: '1.5rem', fontWeight: 800 }}>42% <span style={{ fontSize: '0.65rem', background: '#D1FAE5', color: '#065F46', padding: '0.2rem 0.5rem', borderRadius: 'var(--radius-full)' }}>Optimal</span></div>
          </div>
        </div>

        <div style={{ padding: '0 1.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h3 style={{ margin: 0 }}>Escalation Queue</h3>
          <span style={{ fontSize: '0.75rem', background: '#E2E8F0', padding: '0.2rem 0.5rem', borderRadius: 'var(--radius-full)' }}>
            {error ? 'API Offline' : `Live: ${queue.length} sessions`}
          </span>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', padding: '0 1.5rem', overflowY: 'auto' }}>
          {loading && <div style={{ fontSize: '0.8rem', color: 'var(--on-surface-variant)', textAlign: 'center' }}>Loading queue...</div>}
          
          {queue.length === 0 && !loading && !error && (
             <div style={{ fontSize: '0.8rem', color: 'var(--on-surface-variant)', textAlign: 'center' }}>No escalated sessions.</div>
          )}

          {error && (
             <div style={{ fontSize: '0.8rem', color: '#991B1B', textAlign: 'center', padding: '1rem', backgroundColor: '#FEF2F2', borderRadius: 'var(--radius-md)' }}>
                Unable to reach backend queue API.
             </div>
          )}

          {queue.map((item, idx) => {
            const isActive = activeItem?.session_id === item.session_id;
            return (
              <div 
                key={idx} 
                onClick={() => setActiveItem(item)}
                style={{ 
                    borderLeft: `4px solid ${isActive ? 'var(--primary)' : 'transparent'}`, 
                    backgroundColor: isActive ? 'var(--surface-low)' : 'transparent', 
                    padding: '1rem', 
                    borderRadius: isActive ? '0 var(--radius-md) var(--radius-md) 0' : '0',
                    cursor: 'pointer'
                }}>
                 <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                   <span style={{ fontSize: '0.65rem', background: '#00685F', color: 'white', padding: '0.2rem 0.5rem', borderRadius: 'var(--radius-sm)', fontWeight: 600 }}>{item.tier || 'PRO'}</span>
                   <span style={{ fontSize: '0.75rem', color: isActive ? 'var(--primary)' : 'var(--on-surface-variant)', fontWeight: isActive ? 600 : 400 }}>{isActive ? 'Active Now' : item.wait_time}</span>
                 </div>
                 <h4 style={{ margin: '0 0 0.25rem 0', fontSize: '0.9rem' }}>{item.title || 'Support Escalation'}</h4>
                 <div style={{ display: 'flex', gap: '1rem', fontSize: '0.75rem', color: 'var(--on-surface-variant)' }}>
                   <span style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}><Activity size={12} /> Conf: {item.confidence || 0.45}</span>
                 </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Main Transcript View */}
      <div style={{ flex: 1, padding: '2rem 4rem', display: 'flex', flexDirection: 'column' }}>
        
        {!activeItem ? (
             <div style={{ margin: 'auto', color: 'var(--on-surface-variant)', textAlign: 'center' }}>
                 Select a session from the queue to assume human control.
             </div>
        ) : (
            <>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                     <div style={{ width: '48px', height: '48px', borderRadius: 'var(--radius-md)', backgroundColor: '#E2E8F0', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                       <Activity size={24} color="var(--primary)" />
                     </div>
                     <div>
                       <h2 className="display" style={{ margin: 0, fontSize: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                         {activeItem.title || 'Agent Trace'} <span style={{ fontSize: '0.65rem', background: '#991B1B', color: 'white', padding: '0.2rem 0.6rem', borderRadius: 'var(--radius-sm)', fontWeight: 800 }}>OPERATOR VIEW</span>
                       </h2>
                       <div style={{ fontSize: '0.85rem', color: 'var(--on-surface-variant)' }}>Session ID: {activeItem.session_id}</div>
                     </div>
                  </div>
                  <button 
                    className="btn-primary" 
                    onClick={handleTakeover}
                    disabled={activeItem.takenOver}
                  >
                     <Users size={18} /> {activeItem.takenOver ? 'In Control' : 'Take Over'}
                  </button>
                </div>

                <div style={{ display: 'flex', gap: '1.5rem', marginBottom: '3rem' }}>
                  <div style={{ flex: 1, backgroundColor: '#FEF2F2', padding: '1.5rem', borderRadius: 'var(--radius-md)' }}>
                     <div className="label" style={{ color: '#991B1B', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}><ShieldAlert size={16} /> ESCALATION REASONING</div>
                     <p style={{ margin: 0, fontSize: '0.9rem', color: '#7F1D1D' }}>
                       {activeItem.reason || "The agent entered a recursive logic loop. Immediate human oversight required."}
                     </p>
                  </div>
                </div>

                {/* Transcript Placeholder */}
                <h3 className="label" style={{ marginBottom: '1.5rem' }}>TRANSCRIPT HISTORY</h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', flex: 1, overflowY: 'auto', paddingBottom: '2rem' }}>
                   <div style={{ fontSize: '0.85rem', color: 'var(--on-surface-variant)' }}>Historical context is mapped via REST interface fetching `/api/escalation/history/{activeItem.session_id}`...</div>
                   {activeItem.takenOver && (
                     <div style={{ padding: '1rem', backgroundColor: 'var(--surface-low)', borderRadius: 'var(--radius-md)', border: '1px dashed var(--primary)' }}>
                        <strong>HUMAN AGENT JOINED:</strong> You are now broadcasting directly to the customer.
                     </div>
                   )}
                </div>

                <div style={{ marginTop: 'auto', paddingTop: '2rem' }}>
                  <form onSubmit={handleSendMessage} className="glass-panel" style={{ display: 'flex', padding: '0.5rem', borderRadius: '1rem', backgroundColor: '#E2E8F0', alignItems: 'center' }}>
                     <input 
                       type="text" 
                       value={message}
                       onChange={(e) => setMessage(e.target.value)}
                       placeholder={activeItem.takenOver ? "Type your reply to the customer..." : "Click 'Take Over' to start assisting..."} 
                       disabled={!activeItem.takenOver || sending}
                       style={{ flex: 1, backgroundColor: 'transparent', border: 'none', outline: 'none', padding: '0.75rem 1rem', fontSize: '1rem', color: 'var(--on-surface)' }}
                     />
                     <button 
                        type="submit"
                        disabled={!activeItem.takenOver || !message.trim() || sending} 
                        style={{ backgroundColor: (activeItem.takenOver && message.trim()) ? 'var(--primary)' : '#CBD5E1', color: 'white', borderRadius: '50%', width: '48px', height: '48px', display: 'flex', alignItems: 'center', justifyContent: 'center', border: 'none', cursor: 'pointer' }}
                      >
                       <Send size={20} />
                     </button>
                  </form>
                </div>
            </>
        )}

      </div>
    </div>
  );
}
