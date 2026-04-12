import React, { useState, useEffect } from 'react';
import { Database, Search, ChevronRight, Activity, ShieldAlert, CheckCircle } from 'lucide-react';

export default function LogsView() {
  const [sessions, setSessions] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [selectedSession, setSelectedSession] = useState<any>(null);

  const getHeaders = () => {
    const token = localStorage.getItem('mindcx_token');
    return {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    };
  };

  useEffect(() => {
    const fetchSessions = async () => {
      try {
        const response = await fetch('http://localhost:8000/api/escalation/sessions', {
          headers: getHeaders()
        });
        if (response.status === 401 || response.status === 403) {
            setError("Session expired or unauthorized. Please re-login.");
            return;
        }
        if (!response.ok) throw new Error("Failed to fetch sessions");
        const data = await response.json();
        setSessions(data.sessions || []);
      } catch (e) {
        setError(String(e));
      } finally {
        setLoading(false);
      }
    };
    fetchSessions();
  }, []);

  const filtered = sessions.filter(s => 
    s.session_id.toLowerCase().includes(search.toLowerCase()) ||
    s.user_id.toLowerCase().includes(search.toLowerCase())
  );

  const fetchDetail = async (id: string) => {
    try {
      const response = await fetch(`http://localhost:8000/api/escalation/session/${id}`, {
        headers: getHeaders()
      });
      if (response.ok) {
        const data = await response.json();
        setSelectedSession(data);
      }
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div style={{ display: 'flex', height: '100%' }}>
      {/* Session List */}
      <div style={{ 
        width: selectedSession ? '400px' : '100%', 
        borderRight: selectedSession ? '1px solid var(--surface-low)' : 'none',
        display: 'flex', 
        flexDirection: 'column',
        transition: 'width 0.3s ease'
      }}>
        <div style={{ padding: '2rem', borderBottom: '1px solid var(--surface-low)' }}>
          <h2 style={{ margin: '0 0 1.5rem 0', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <Database color="var(--primary)" /> Session Logs
          </h2>
          <div style={{ position: 'relative' }}>
            <Search size={16} style={{ position: 'absolute', left: '1rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--on-surface-variant)' }} />
            <input 
              type="text" 
              placeholder="Search session or user ID..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{ 
                width: '100%', 
                padding: '0.75rem 1rem 0.75rem 2.5rem', 
                borderRadius: 'var(--radius-md)', 
                border: '1px solid var(--surface-low)',
                backgroundColor: 'var(--surface-lowest)',
                outline: 'none'
              }}
            />
          </div>
        </div>

        <div style={{ flex: 1, overflowY: 'auto' }}>
          {loading ? (
            <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--on-surface-variant)' }}>Loading sessions...</div>
          ) : error ? (
            <div style={{ padding: '2rem', textAlign: 'center', color: '#991B1B' }}>Error: {error}</div>
          ) : filtered.length === 0 ? (
            <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--on-surface-variant)' }}>No sessions found.</div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead style={{ position: 'sticky', top: 0, backgroundColor: 'var(--surface-lowest)', borderBottom: '1px solid var(--surface-low)' }}>
                <tr>
                  <th style={{ textAlign: 'left', padding: '1rem', fontSize: '0.75rem', color: 'var(--on-surface-variant)' }}>SESSION ID</th>
                  <th style={{ textAlign: 'left', padding: '1rem', fontSize: '0.75rem', color: 'var(--on-surface-variant)' }}>TIER</th>
                  <th style={{ textAlign: 'left', padding: '1rem', fontSize: '0.75rem', color: 'var(--on-surface-variant)' }}>OUTCOME</th>
                  {!selectedSession && <th style={{ textAlign: 'left', padding: '1rem', fontSize: '0.75rem', color: 'var(--on-surface-variant)' }}>SPECIALIST</th>}
                  <th style={{ width: '40px' }}></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(s => (
                  <tr 
                    key={s.session_id} 
                    onClick={() => fetchDetail(s.session_id)}
                    style={{ 
                      cursor: 'pointer', 
                      backgroundColor: selectedSession?.session_id === s.session_id ? 'var(--surface-low)' : 'transparent',
                      borderBottom: '1px solid var(--surface-low)'
                    }}
                    className="log-row"
                  >
                    <td style={{ padding: '1rem', fontSize: '0.85rem' }}>
                      <div style={{ fontWeight: 600 }}>{s.session_id}</div>
                      <div style={{ fontSize: '0.7rem', color: 'var(--on-surface-variant)' }}>{s.user_id}</div>
                    </td>
                    <td style={{ padding: '1rem' }}>
                      <span style={{ fontSize: '0.65rem', background: '#E2E8F0', padding: '0.2rem 0.5rem', borderRadius: 'var(--radius-sm)', fontWeight: 600 }}>{s.tier}</span>
                    </td>
                    <td style={{ padding: '1rem' }}>
                       <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.8rem', color: s.outcome === 'Escalated' ? '#991B1B' : '#059669' }}>
                         {s.outcome === 'Escalated' ? <ShieldAlert size={14} /> : <CheckCircle size={14} />}
                         {s.outcome}
                       </div>
                    </td>
                    {!selectedSession && <td style={{ padding: '1rem', fontSize: '0.85rem' }}>{s.specialist.replace('_', ' ').toUpperCase()}</td>}
                    <td style={{ padding: '1rem' }}><ChevronRight size={16} color="var(--on-surface-variant)" /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Trace Detail View */}
      {selectedSession && (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', backgroundColor: 'var(--surface-lowest)' }}>
           <div style={{ padding: '1.5rem 2rem', borderBottom: '1px solid var(--surface-low)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
             <div>
               <h3 style={{ margin: 0 }}>{selectedSession.session_id} Trace</h3>
               <div style={{ fontSize: '0.8rem', color: 'var(--on-surface-variant)' }}>User: {selectedSession.user_id} | Tier: {selectedSession.tier}</div>
             </div>
             <button onClick={() => setSelectedSession(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--on-surface-variant)' }}>Close</button>
           </div>
           
           <div style={{ flex: 1, overflowY: 'auto', padding: '2rem' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
                
                {/* Entities & Notes */}
                <div style={{ display: 'flex', gap: '1rem' }}>
                  <div style={{ flex: 1, backgroundColor: 'var(--surface-low)', padding: '1rem', borderRadius: 'var(--radius-md)' }}>
                    <div className="label" style={{ marginBottom: '0.5rem' }}>Resolved Entities</div>
                    {Object.keys(selectedSession.resolved_entities).length > 0 ? (
                      <ul style={{ margin: 0, paddingLeft: '1.2rem', fontSize: '0.85rem' }}>
                        {Object.entries(selectedSession.resolved_entities).map(([k, v]) => (
                          <li key={k}><strong>{k}:</strong> {String(v)}</li>
                        ))}
                      </ul>
                    ) : <div style={{ fontSize: '0.85rem', fontStyle: 'italic' }}>None</div>}
                  </div>
                  <div style={{ flex: 1, backgroundColor: 'var(--surface-low)', padding: '1rem', borderRadius: 'var(--radius-md)' }}>
                    <div className="label" style={{ marginBottom: '0.5rem' }}>State Summary</div>
                    <div style={{ fontSize: '0.85rem' }}>{selectedSession.state_note || "No summary available."}</div>
                  </div>
                </div>

                {/* Routing Decisions */}
                <div>
                  <div className="label" style={{ marginBottom: '1rem' }}>Routing Trace</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                    {selectedSession.routing_decisions.map((d: any, i: number) => (
                      <div key={i} style={{ display: 'flex', gap: '1rem', alignItems: 'center', fontSize: '0.85rem', padding: '0.75rem', backgroundColor: 'var(--surface-low)', borderRadius: 'var(--radius-sm)' }}>
                        <div style={{ fontWeight: 600, color: 'var(--primary)' }}>{d.intent.toUpperCase()}</div>
                        <div style={{ color: 'var(--on-surface-variant)' }}>→</div>
                        <div style={{ fontWeight: 600 }}>{d.specialist.replace('_', ' ').toUpperCase()}</div>
                        <div style={{ flex: 1, fontSize: '0.75rem', fontStyle: 'italic', textAlign: 'right' }}>{d.context_note}</div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Transcript */}
                <div>
                  <div className="label" style={{ marginBottom: '1rem' }}>Full Transcript</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                    {selectedSession.message_history.map((m: any, i: number) => (
                      <div key={i} style={{ 
                        padding: '1rem', 
                        borderRadius: 'var(--radius-md)', 
                        backgroundColor: m.role === 'user' ? '#F8FAFC' : '#F1F5F9',
                        borderLeft: `4px solid ${m.role === 'user' ? '#CBD5E1' : 'var(--primary)'}`
                      }}>
                        <div style={{ fontSize: '0.7rem', fontWeight: 800, marginBottom: '0.4rem', color: m.role === 'user' ? '#64748B' : 'var(--primary)' }}>{m.role.toUpperCase()}</div>
                        <div style={{ fontSize: '0.9rem', lineHeight: 1.5 }}>{m.content}</div>
                      </div>
                    ))}
                  </div>
                </div>

              </div>
           </div>
        </div>
      )}
    </div>
  );
}
