import React from 'react';
import { Bell, Settings, User, ShieldCheck, LogOut } from 'lucide-react';

interface HeaderProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  isAgent?: boolean;
  onLogout?: () => void;
}

export default function Header({ activeTab, setActiveTab, isAgent = false, onLogout }: HeaderProps) {
  const tabs = isAgent 
    ? ['Dashboard', 'Live Traces', 'Logs'] 
    : ['Live Support'];

  return (
    <header style={{ 
      display: 'flex', 
      alignItems: 'center', 
      padding: '1rem 2rem', 
      backgroundColor: isAgent ? 'var(--surface-lowest)' : 'var(--primary-container)',
      height: '70px',
      position: 'sticky',
      top: 0,
      zIndex: 10,
      borderBottom: isAgent ? '2px solid var(--primary)' : 'none'
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '3rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <h2 style={{ color: isAgent ? 'var(--primary)' : 'var(--on-primary-container)', margin: 0, fontSize: '1.25rem' }}>MindCX Support</h2>
          {isAgent && (
            <div style={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: '0.5rem', 
              padding: '0.25rem 0.75rem', 
              backgroundColor: 'rgba(0, 104, 95, 0.1)', 
              borderRadius: '20px',
              border: '1px solid var(--primary)'
            }}>
              <ShieldCheck size={14} color="var(--primary)" />
              <span style={{ fontSize: '0.75rem', fontWeight: 800, color: 'var(--primary)', letterSpacing: '0.05em' }}>OPERATOR VIEW</span>
            </div>
          )}
        </div>
        <nav style={{ display: 'flex', gap: '2rem' }}>
          {tabs.map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              style={{
                background: 'none',
                color: activeTab === tab ? 'var(--primary)' : 'var(--on-surface-variant)',
                fontWeight: activeTab === tab ? 600 : 500,
                fontSize: '1rem',
                borderBottom: activeTab === tab ? '2px solid var(--primary)' : 'none',
                paddingBottom: '0.25rem',
                marginBottom: '-0.25rem',
                border: 'none',
                cursor: 'pointer'
              }}
            >
              {tab}
            </button>
          ))}
        </nav>
      </div>
      <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '1.5rem', color: 'var(--on-surface-variant)' }}>
        <Bell size={20} style={{cursor:'pointer'}} />
        <Settings size={20} style={{cursor:'pointer'}} />
        {onLogout && (
          <button 
            onClick={onLogout}
            style={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: '0.5rem', 
              background: 'none', 
              border: 'none', 
              cursor: 'pointer',
              color: 'var(--on-surface-variant)',
              fontSize: '0.85rem',
              fontWeight: 500
            }}
          >
            <LogOut size={18} /> Logout
          </button>
        )}
        <div style={{ width: '32px', height: '32px', borderRadius: '50%', backgroundColor: '#E2E8F0', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <User size={18} />
        </div>
      </div>
    </header>
  );
}
