import { useState, useEffect } from 'react'
import Navbar from './components/Navbar'
import Landing from './pages/Landing'
import Login from './pages/Login'
import Register from './pages/Register'
import Upload from './pages/Upload'
import Invoices from './pages/Invoices'

export default function App() {
  const [page, setPage] = useState('landing')
  const [user, setUser] = useState(() => {
    const token = localStorage.getItem('token')
    const email = localStorage.getItem('email')
    return token && email ? email : null
  })

  useEffect(() => {
    if (!user && page !== 'landing' && page !== 'login' && page !== 'register') {
      setPage('login')
    }
  }, [user, page])

  function handleLogin(email) {
    localStorage.setItem('email', email)
    setUser(email)
    setPage('upload')
  }

  function handleLogout() {
    localStorage.removeItem('token')
    localStorage.removeItem('email')
    setUser(null)
    setPage('landing')
  }

  const base = { minHeight: '100vh', background: 'linear-gradient(180deg, #f5f5f7, #eaeaec)', fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" }

  if (page === 'landing') {
    return (
      <div style={base}>
        <Landing onEnter={() => setPage(user ? 'upload' : 'login')} />
      </div>
    )
  }

  if (page === 'login') {
    return (
      <div style={base}>
        <Login onLogin={handleLogin} onSwitch={() => setPage('register')} />
      </div>
    )
  }

  if (page === 'register') {
    return (
      <div style={base}>
        <Register onLogin={handleLogin} onSwitch={() => setPage('login')} />
      </div>
    )
  }

  return (
    <div style={base}>
      <Navbar page={page} setPage={setPage} user={user} onLogout={handleLogout} />
      {page === 'upload' ? <Upload /> : <Invoices />}
    </div>
  )
}
