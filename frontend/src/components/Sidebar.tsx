import React from 'react';
import { Plus, Users, ShieldCheck, Database, ListEnd, Cpu } from 'lucide-react';

export interface SidebarContext {
  tier: string;
  user_id?: string;
  intent?: string;
  specialist?: string;
  tools?: string[];
  lastNode?: string;
}

interface SidebarProps {
  context?: SidebarContext;
}

export default function Sidebar({ context }: SidebarProps) {
  const activeNode = context?.lastNode || '';
  
  const items = [
    { icon: <Cpu size={18} />, label: 'Concierge', active: activeNode === 'concierge' },
    { icon: <Users size={18} />, label: 'Specialist', active: ['billing_specialist', 'tech_specialist'].includes(activeNode) },
    { icon: <ShieldCheck size={18} />, label: 'Quality Lead', active: activeNode === 'quality_lead' },
    { icon: <Database size={18} />, label: 'Memory', active: false },
    { icon: <ListEnd size={18} />, label: 'Trace', active: false },
  ];

  return (
    <aside style={{
      width: '260px',
      backgroundColor: 'var(--surface-low)',
      padding: '2rem 1.5rem',
      display: 'flex',
      flexDirection: 'column',
      gap: '2rem',
      flexShrink: 0
    }}>
      <div>
        <div className="label" style={{ marginBottom: '1.5rem', display: 'flex', alignItems:'center', gap:'0.5rem' }}>
          <span style={{color: 'var(--primary)'}}>&#9646;</span> Session Context
        </div>
        <div style={{ fontSize: '0.75rem', color: 'var(--on-surface-variant)', letterSpacing: '0.05em' }}>MULTI-AGENT SYSTEM</div>
      </div>

      <div style={{
        backgroundColor: 'var(--surface-lowest)',
        borderRadius: 'var(--radius-md)',
        padding: '1.25rem',
        boxShadow: 'var(--shadow-ambient)',
        borderLeft: '4px solid var(--primary)'
      }}>
        <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '0.65rem', background: '#00685F', color: 'white', padding: '0.2rem 0.5rem', borderRadius: 'var(--radius-sm)', fontWeight: 600 }}>{context?.tier || 'PRO'} TIER</span>
          {context?.user_id && <span style={{ fontSize: '0.65rem', background: '#D1FAE5', color: '#065F46', padding: '0.2rem 0.5rem', borderRadius: 'var(--radius-sm)', fontWeight: 600 }}>ID: {context.user_id}</span>}
        </div>
        <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '0.9rem' }}>{context?.intent ? context.intent.toUpperCase() : 'Routing...'}</h4>
        <p style={{ fontSize: '0.8rem', color: 'var(--on-surface-variant)', fontStyle: 'italic', margin: 0 }}>
          {context?.specialist ? `Routed to ${context.specialist.replace('_', ' ')}` : 'Awaiting specialist assignment...'}
        </p>
        {context?.tools && context.tools.length > 0 && (
          <div style={{ marginTop: '0.75rem', display: 'flex', flexWrap: 'wrap', gap: '0.25rem' }}>
            {context.tools.map(t => (
               <span key={t} style={{ fontSize: '0.6rem', color: 'var(--primary)', background: 'rgba(0, 104, 95, 0.1)', padding: '0.1rem 0.3rem', borderRadius: '2px' }}>{t} ✓</span>
            ))}
          </div>
        )}
      </div>

      <nav style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', flex: 1 }}>
        {items.map((item, idx) => (
          <div key={idx} style={{
            display: 'flex',
            alignItems: 'center',
            gap: '1rem',
            padding: '0.75rem 1rem',
            borderRadius: 'var(--radius-md)',
            backgroundColor: item.active ? 'var(--surface-lowest)' : 'transparent',
            color: item.active ? 'var(--primary)' : 'var(--on-surface-variant)',
            fontWeight: item.active ? 600 : 500,
            cursor: 'pointer',
            boxShadow: item.active ? 'var(--shadow-ambient)' : 'none',
            transition: 'all 0.2s ease'
          }}>
            {item.icon}
            <span style={{ fontSize: '0.9rem' }}>{item.label}</span>
            {item.active && <span style={{ marginLeft: 'auto', width: '8px', height: '8px', backgroundColor: 'var(--primary)', borderRadius: '50%', boxShadow: '0 0 8px var(--primary)' }}></span>}
          </div>
        ))}
      </nav>

      <button className="btn-primary" style={{ marginTop: 'auto' }} onClick={() => window.location.reload()}>
        <Plus size={18} /> New Session
      </button>
    </aside>
  );
}
