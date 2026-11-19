import React from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Bell, Building2, CalendarClock, ClipboardList, FileBarChart, Gauge as GaugeIcon, History, LayoutDashboard, ListChecks, Monitor, Settings as SettingsIcon, TicketCheck, TrendingUp, User as UserIcon, Users } from 'lucide-react'
import './index.css'
import { AuthProvider, useAuth } from './lib/auth'
import { Shell } from './components/Shell'
import { Spinner, ToastProvider } from './components/ui'
import Landing from './pages/Landing'
import Login from './pages/Login'
import CustomerHome from './pages/customer/Home'
import Join from './pages/customer/Join'
import Token from './pages/customer/Token'
import Tokens from './pages/customer/History'
import Notifications from './pages/customer/Notifications'
import Profile from './pages/customer/Profile'
import Overview from './pages/admin/Overview'
import LiveQueue from './pages/admin/LiveQueue'
import Counters from './pages/admin/Counters'
import Forecast from './pages/admin/Forecast'
import MLMonitor from './pages/admin/MLMonitor'
import Reports from './pages/admin/Reports'
import Settings from './pages/admin/Settings'
import Organizations from './pages/admin/Organizations'

const CUSTOMER_NAV = [
  { to: '/app', icon: LayoutDashboard, label: 'Home', end: true },
  { to: '/app/join', icon: TicketCheck, label: 'Join queue' },
  { to: '/app/history', icon: History, label: 'History' },
  { to: '/app/notifications', icon: Bell, label: 'Alerts' },
  { to: '/app/profile', icon: UserIcon, label: 'Profile' },
]
const ADMIN_NAV = [
  { to: '/admin', icon: LayoutDashboard, label: 'Overview', end: true },
  { to: '/admin/queue', icon: ListChecks, label: 'Live queue' },
  { to: '/admin/counters', icon: Users, label: 'Counters & staff' },
  { to: '/admin/forecast', icon: TrendingUp, label: 'Forecast & alerts' },
  { to: '/admin/ml', icon: Monitor, label: 'ML monitoring' },
  { to: '/admin/reports', icon: FileBarChart, label: 'Reports' },
  { to: '/admin/organizations', icon: Building2, label: 'Organizations' },
  { to: '/admin/settings', icon: SettingsIcon, label: 'Settings' },
]

function Guard({ staff, children }) {
  const { user, loading } = useAuth()
  if (loading) return <Spinner />
  if (!user) return <Navigate to="/login" replace />
  if (staff && user.role === 'customer') return <Navigate to="/app" replace />
  if (!staff && user.role !== 'customer') return <Navigate to="/admin" replace />
  return children
}

function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/app" element={<Guard><Shell nav={CUSTOMER_NAV} area="Customer" /></Guard>}>
        <Route index element={<CustomerHome />} />
        <Route path="join" element={<Join />} />
        <Route path="token/:id" element={<Token />} />
        <Route path="history" element={<Tokens />} />
        <Route path="notifications" element={<Notifications />} />
        <Route path="profile" element={<Profile />} />
      </Route>
      <Route path="/admin" element={<Guard staff><Shell nav={ADMIN_NAV} area="Operations" /></Guard>}>
        <Route index element={<Overview />} />
        <Route path="queue" element={<LiveQueue />} />
        <Route path="counters" element={<Counters />} />
        <Route path="forecast" element={<Forecast />} />
        <Route path="ml" element={<MLMonitor />} />
        <Route path="reports" element={<Reports />} />
        <Route path="organizations" element={<Organizations />} />
        <Route path="settings" element={<Settings />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <ToastProvider>
          <App />
        </ToastProvider>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
)
