import React, { useState, useEffect } from 'react';
import Header from './components/Header';
import Sidebar from './components/Sidebar';
import ChatView from './pages/ChatView';
import Login from './pages/Login';
import { SidebarContext } from './components/Sidebar';

function App() {
  const [user, setUser] = useState<any>(null);
  const [sidebarContext, setSidebarContext] = useState<SidebarContext>({
    tier: 'PRO'
  });

  useEffect(() => {
    const storedUser = localStorage.getItem('mindcx_user');
    if (storedUser) {
      setUser(JSON.parse(storedUser));
    }
  }, []);

  if (!user) {
    return <Login onLoginSuccess={setUser} />;
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>
      <Header 
        activeTab="Live Support" 
        setActiveTab={() => {}} 
        isAgent={false} 
        onLogout={() => { localStorage.clear(); setUser(null); }} 
      />
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <Sidebar context={sidebarContext} />
        <main style={{ flex: 1, overflowY: 'auto' }}>
          <ChatView onContextUpdate={setSidebarContext} />
        </main>
      </div>
    </div>
  );
}

export default App;
