import React, { useState, useEffect } from 'react';
import Header from './components/Header';
import Sidebar from './components/Sidebar';
import ChatView from './pages/ChatView';
import EscalationDashboard from './pages/EscalationDashboard';
import LogsView from './pages/LogsView';
import Login from './pages/Login';
import { SidebarContext } from './components/Sidebar';
import { User } from './api/client';

function AgentApp() {
  const [user, setUser] = useState<User | null>(null);
  const [activeTab, setActiveTab] = useState('Dashboard');
  const [sidebarContext, setSidebarContext] = useState<SidebarContext>({
    tier: 'PRO'
  });

  useEffect(() => {
    const storedUser = localStorage.getItem('mindcx_user');
    if (storedUser) {
      const u = JSON.parse(storedUser);
      if (['agent', 'admin'].includes(u.role)) {
        setUser(u);
      } else {
        localStorage.clear();
      }
    }
  }, []);

  if (!user) {
    return <Login onLoginSuccess={setUser} isAgentPortal={true} />;
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>
      <Header 
        activeTab={activeTab} 
        setActiveTab={setActiveTab} 
        isAgent={true} 
        onLogout={() => { localStorage.clear(); setUser(null); }}
      />
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <Sidebar context={sidebarContext} />
        <main style={{ flex: 1, overflowY: 'auto' }}>
          <div style={{ display: activeTab === 'Dashboard' ? 'block' : 'none', height: '100%' }}>
            <EscalationDashboard />
          </div>
          <div style={{ display: activeTab === 'Live Traces' ? 'block' : 'none', height: '100%' }}>
            <ChatView onContextUpdate={setSidebarContext} />
          </div>
          <div style={{ display: activeTab === 'Logs' ? 'block' : 'none', height: '100%' }}>
            <LogsView />
          </div>
        </main>
      </div>
    </div>
  );
}

export default AgentApp;
