import { Toaster } from 'react-hot-toast'
import { Dashboard } from './components/Dashboard'
import { Footer } from './components/Footer'
import { Header } from './components/Header'
import { Landing } from './components/Landing'
import { useAuth } from './hooks/useAuth'

export default function App() {
  const auth = useAuth()
  const signedIn = auth.token !== null

  return (
    <div className="flex min-h-dvh flex-col">
      <Header username={auth.username} onSignOut={signedIn ? auth.signOut : undefined} />
      <main className="flex-1">{signedIn ? <Dashboard /> : <Landing auth={auth} />}</main>
      <Footer />
      <Toaster
        position="bottom-center"
        toastOptions={{
          style: {
            background: 'var(--surface)',
            color: 'var(--text)',
            border: '1px solid var(--line)',
            fontSize: '14px',
          },
        }}
      />
    </div>
  )
}
