import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { 
  Link, Zap, BarChart2, Shield, Server, 
  MonitorSmartphone, Copy, Search,
  ChevronDown, ExternalLink, ArrowRight, Share2, ArrowLeft
} from 'lucide-react'
import toast, { Toaster } from 'react-hot-toast'
import { Button } from './components/ui/button'
import { Input } from './components/ui/input'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './components/ui/card'
import { cn } from './lib/utils'

const API_BASE = '' // relative URL since Nginx will proxy

type View = 'home' | 'privacy' | 'terms' | 'cookies' | 'disclaimer'

export default function App() {
  const [token, setToken] = useState<string | null>(localStorage.getItem('token'))
  const [view, setView] = useState<View>('home')

  useEffect(() => {
    if (token) {
      localStorage.setItem('token', token)
    } else {
      localStorage.removeItem('token')
    }
  }, [token])

  const renderContent = () => {
    if (view === 'privacy') return <LegalPage title="Privacy Policy" onBack={() => setView('home')} content="This is a template Privacy Policy. We take your privacy seriously. All data is encrypted and securely stored. We only use strictly necessary cookies to keep you logged in. We do not sell your data." />
    if (view === 'terms') return <LegalPage title="Terms of Service" onBack={() => setView('home')} content="This is a template Terms of Service. By using Short.io you agree to not shorten links to malicious, illegal, or abusive content. We reserve the right to terminate accounts that violate these terms." />
    if (view === 'cookies') return <LegalPage title="Cookie Policy" onBack={() => setView('home')} content="This is a template Cookie Policy. We use a single JWT token in your LocalStorage to keep you authenticated. We do not use third-party tracking cookies." />
    if (view === 'disclaimer') return <LegalPage title="Disclaimer" onBack={() => setView('home')} content="This is a template Disclaimer. Short.io is provided 'as is' without warranties of any kind. We are not responsible for the content of the websites you are redirected to." />
    
    return token ? <Dashboard token={token} /> : <LandingPage setToken={setToken} />
  }

  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col font-sans">
      <Toaster position="bottom-right" />
      <Navbar token={token} setToken={setToken} setView={setView} />
      <main className="flex-1 flex flex-col">
        {renderContent()}
      </main>
      <Footer setView={setView} />
    </div>
  )
}

function Navbar({ token, setToken, setView }: { token: string | null, setToken: (t: string | null) => void, setView: (v: View) => void }) {
  return (
    <nav className="sticky top-0 z-50 w-full border-b border-border/40 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container mx-auto max-w-6xl px-4 h-16 flex items-center justify-between">
        <div 
          className="flex items-center gap-2 font-bold text-xl tracking-tight cursor-pointer" 
          onClick={() => setView('home')}
        >
          <Link className="h-6 w-6 text-primary" />
          <span>Short<span className="text-primary">.io</span></span>
        </div>
        <div className="flex items-center gap-4">
          {!token ? (
            <a href="#auth" onClick={() => setView('home')} className="text-sm font-medium hover:text-primary transition-colors">
              Sign In
            </a>
          ) : (
            <Button variant="ghost" size="sm" onClick={() => { setToken(null); setView('home') }}>
              Sign Out
            </Button>
          )}
        </div>
      </div>
    </nav>
  )
}

function LegalPage({ title, content, onBack }: { title: string, content: string, onBack: () => void }) {
  return (
    <div className="container mx-auto max-w-3xl px-4 py-24 flex-1">
      <Button variant="ghost" className="mb-8" onClick={onBack}>
        <ArrowLeft className="mr-2 h-4 w-4" /> Back to Home
      </Button>
      <h1 className="text-4xl font-bold tracking-tight mb-8">{title}</h1>
      <div className="prose prose-slate dark:prose-invert">
        <p className="text-lg leading-relaxed text-muted-foreground">{content}</p>
        <div className="mt-12 p-4 bg-yellow-500/10 border border-yellow-500/20 rounded-md">
          <p className="text-sm text-yellow-600 dark:text-yellow-400 font-medium">
            Note: This is a placeholder document. You must replace this with a legally binding document before launching the product.
          </p>
        </div>
      </div>
    </div>
  )
}

function LandingPage({ setToken }: { setToken: (t: string) => void }) {
  return (
    <div className="flex-1">
      {/* Hero */}
      <section className="container mx-auto max-w-6xl px-4 pt-24 pb-32">
        <div className="grid lg:grid-cols-2 gap-12 items-center">
          <div className="max-w-2xl space-y-8">
            <h1 className="text-5xl sm:text-6xl font-bold tracking-tight text-foreground leading-[1.1]">
              Shorten, Share, <span className="text-primary">Track.</span>
            </h1>
            <p className="text-lg sm:text-xl text-muted-foreground leading-relaxed">
              A fast, secure, and reliable URL shortener that transforms long links into clean, shareable URLs in seconds.
            </p>
            <div className="flex flex-wrap gap-4">
              <Button size="lg" className="h-12 px-8 text-base shadow-lg shadow-primary/20" onClick={() => document.getElementById('auth')?.scrollIntoView({ behavior: 'smooth' })}>
                Get Started <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
              <Button variant="outline" size="lg" className="h-12 px-8 text-base">
                Learn More
              </Button>
            </div>
          </div>
          
          {/* Mock Browser Window */}
          <div className="relative mx-auto w-full max-w-lg hidden lg:block">
            <div className="rounded-xl border border-border/50 bg-card shadow-2xl overflow-hidden">
              <div className="h-10 bg-muted/50 border-b border-border flex items-center px-4 gap-2">
                <div className="flex gap-1.5">
                  <div className="w-3 h-3 rounded-full bg-red-500/80"></div>
                  <div className="w-3 h-3 rounded-full bg-yellow-500/80"></div>
                  <div className="w-3 h-3 rounded-full bg-green-500/80"></div>
                </div>
                <div className="mx-auto bg-background/50 rounded-md text-xs text-muted-foreground px-24 py-1 border border-border/50 flex items-center gap-2">
                  <LockIcon className="w-3 h-3" /> short.io/dashboard
                </div>
              </div>
              <div className="p-6 space-y-4">
                <div className="flex justify-between items-center">
                  <div className="space-y-1">
                    <div className="h-4 w-24 bg-primary/20 rounded"></div>
                    <div className="h-8 w-48 bg-muted rounded"></div>
                  </div>
                  <div className="h-12 w-12 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold">42k</div>
                </div>
                <div className="h-32 bg-muted/30 rounded-lg border border-border/50 flex items-end p-4 gap-2">
                  {[40, 70, 45, 90, 65, 85, 100].map((h, i) => (
                    <div key={i} className="flex-1 bg-primary/80 rounded-t-sm transition-all duration-1000" style={{ height: `${h}%` }}></div>
                  ))}
                </div>
              </div>
            </div>
            <div className="absolute -z-10 top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full h-full bg-primary/20 blur-[100px] rounded-full"></div>
          </div>
        </div>
      </section>

      {/* Auth Gateway */}
      <section id="auth" className="bg-muted/30 border-y border-border py-24">
        <div className="container mx-auto max-w-md px-4">
          <AuthCard setToken={setToken} />
        </div>
      </section>

      {/* Features */}
      <section className="container mx-auto max-w-6xl px-4 py-32">
        <div className="text-center max-w-2xl mx-auto mb-16">
          <h2 className="text-3xl font-bold mb-4">Enterprise-grade features</h2>
          <p className="text-muted-foreground text-lg">Everything you need to manage your links at scale.</p>
        </div>
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[
            { icon: Zap, title: "Fast Redirects", desc: "Powered by in-memory Redis caching for sub-millisecond resolution." },
            { icon: BarChart2, title: "Analytics Ready", desc: "Track clicks globally with real-time asynchronous processing." },
            { icon: Shield, title: "Secure Links", desc: "XSS-protected, rate-limited, and JWT authenticated architecture." },
            { icon: Share2, title: "Easy Sharing", desc: "Instantly copy short URLs or generate high-quality QR codes." },
            { icon: Server, title: "Reliable Infrastructure", desc: "Built on top of a robust PostgreSQL cluster for maximum uptime." },
            { icon: MonitorSmartphone, title: "Responsive Design", desc: "Manage your links on any device with a flawless mobile experience." }
          ].map((feature, i) => (
            <Card key={i} className="bg-card hover:-translate-y-1 transition-transform duration-300 border-border/50">
              <CardHeader>
                <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center text-primary mb-4">
                  <feature.icon className="w-5 h-5" />
                </div>
                <CardTitle className="text-xl">{feature.title}</CardTitle>
                <CardDescription className="text-sm mt-2">{feature.desc}</CardDescription>
              </CardHeader>
            </Card>
          ))}
        </div>
      </section>

      {/* How it Works */}
      <section className="bg-muted/30 py-32">
        <div className="container mx-auto max-w-6xl px-4">
          <div className="text-center max-w-2xl mx-auto mb-16">
            <h2 className="text-3xl font-bold mb-4">How it works</h2>
            <p className="text-muted-foreground">Four simple steps to better link management.</p>
          </div>
          <div className="grid md:grid-cols-4 gap-8 text-center relative">
            <div className="hidden md:block absolute top-1/2 left-0 w-full h-0.5 bg-border -z-10 -translate-y-1/2"></div>
            {[
              { step: 1, title: "Paste URL", desc: "Enter your long, complicated link" },
              { step: 2, title: "Shorten", desc: "We generate a secure, unique alias" },
              { step: 3, title: "Share", desc: "Distribute your new clean link" },
              { step: 4, title: "Track", desc: "Monitor clicks in real-time" }
            ].map((s, i) => (
              <div key={i} className="flex flex-col items-center">
                <div className="w-12 h-12 rounded-full bg-background border-2 border-primary flex items-center justify-center font-bold text-lg mb-6 shadow-sm">
                  {s.step}
                </div>
                <h4 className="font-semibold text-lg mb-2">{s.title}</h4>
                <p className="text-sm text-muted-foreground">{s.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section className="container mx-auto max-w-3xl px-4 py-32">
        <div className="text-center mb-12">
          <h2 className="text-3xl font-bold">Frequently Asked Questions</h2>
        </div>
        <div className="space-y-4">
          {[
            { q: "What is a URL shortener?", a: "It's a tool that takes a long, unwieldy URL and converts it into a shorter, more manageable link that redirects to the original destination." },
            { q: "How long do shortened links last?", a: "As long as your account is active, your links will remain functional permanently. We do not expire active links." },
            { q: "Are my links secure?", a: "Yes. All links are served over HTTPS, and our backend employs strict validation and rate-limiting to prevent abuse." },
            { q: "Can I choose my own short URL?", a: "Absolutely! You can provide a custom alias during link creation. If it's available, it's yours." }
          ].map((faq, i) => (
            <FaqItem key={i} question={faq.q} answer={faq.a} />
          ))}
        </div>
      </section>
    </div>
  )
}

function FaqItem({ question, answer }: { question: string, answer: string }) {
  const [isOpen, setIsOpen] = useState(false)
  
  return (
    <div className="border border-border rounded-lg bg-card overflow-hidden">
      <button 
        className="w-full px-6 py-4 flex justify-between items-center focus:outline-none focus-visible:bg-muted/50"
        onClick={() => setIsOpen(!isOpen)}
      >
        <span className="font-medium text-left">{question}</span>
        <ChevronDown className={cn("w-5 h-5 text-muted-foreground transition-transform duration-200", isOpen && "rotate-180")} />
      </button>
      <AnimatePresence>
        {isOpen && (
          <motion.div 
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            <div className="px-6 pb-4 pt-0 text-muted-foreground text-sm border-t border-border/50 mt-2 pt-4">
              {answer}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function AuthCard({ setToken }: { setToken: (t: string) => void }) {
  const [isLogin, setIsLogin] = useState(true)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    
    try {
      if (isLogin) {
        const formData = new URLSearchParams()
        formData.append("username", username)
        formData.append("password", password)
        
        const res = await fetch(`${API_BASE}/token`, {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body: formData.toString()
        })
        const data = await res.json()
        
        // OAuth2 format returns token directly, or error
        if (res.ok) {
          toast.success("Welcome back!")
          setToken(data.access_token)
        } else {
          const errMsg = data.message || (typeof data.detail === 'string' ? data.detail : (Array.isArray(data.detail) ? data.detail[0].msg : "Login failed"))
          toast.error(errMsg)
        }
      } else {
        const res = await fetch(`${API_BASE}/register`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username, password })
        })
        const data = await res.json()
        
        if (data.success || res.ok) {
          toast.success("Account created! Please log in.")
          setIsLogin(true)
          setPassword('')
        } else {
          const errMsg = data.message || (typeof data.detail === 'string' ? data.detail : (Array.isArray(data.detail) ? data.detail[0].msg : "Registration failed"))
          toast.error(errMsg)
        }
      }
    } catch (err) {
      toast.error("Network error occurred")
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card className="w-full shadow-xl">
      <CardHeader className="text-center space-y-1">
        <CardTitle className="text-2xl font-bold">{isLogin ? 'Welcome back' : 'Create an account'}</CardTitle>
        <CardDescription>
          {isLogin ? 'Enter your credentials to access your workspace' : 'Sign up for enterprise link management'}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex p-1 bg-muted rounded-lg mb-6">
          <button 
            className={cn("flex-1 py-1.5 text-sm font-medium rounded-md transition-colors", isLogin ? "bg-background shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground")}
            onClick={() => setIsLogin(true)}
          >
            Log In
          </button>
          <button 
            className={cn("flex-1 py-1.5 text-sm font-medium rounded-md transition-colors", !isLogin ? "bg-background shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground")}
            onClick={() => setIsLogin(false)}
          >
            Register
          </button>
        </div>
        
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <label className="text-sm font-medium leading-none">Username</label>
            <Input required value={username} onChange={e => setUsername(e.target.value)} placeholder="name@company.com" />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium leading-none">Password</label>
            <Input required type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="••••••••" />
          </div>
          <Button type="submit" className="w-full mt-2" disabled={loading}>
            {loading ? "Processing..." : isLogin ? "Log In" : "Sign Up"}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}

function Dashboard({ token }: { token: string }) {
  const [stats, setStats] = useState({ clicks: 0, links: 0 })
  const [history, setHistory] = useState<any[]>([])
  const [longUrl, setLongUrl] = useState('')
  const [customAlias, setCustomAlias] = useState('')
  const [isShortening, setIsShortening] = useState(false)
  const [search, setSearch] = useState('')

  const fetchDashboard = async () => {
    try {
      const res = await fetch(`${API_BASE}/dashboard`, {
        headers: { "Authorization": `Bearer ${token}` }
      })
      const respData = await res.json()
      if (respData.success) {
        const data = respData.data
        setStats({
          clicks: data["Total Network Clicks"] || 0,
          links: data["Dashboard"]?.length || 0
        })
        setHistory(data["Dashboard"] || [])
      } else {
        toast.error(respData.message || "Failed to load dashboard data")
      }
    } catch (e) {
      toast.error("Network error while loading dashboard")
    }
  }

  useEffect(() => {
    fetchDashboard()
  }, [token])

  const handleShorten = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsShortening(true)
    
    try {
      const payload: any = { long_url: longUrl }
      if (customAlias) payload.custom_id = customAlias

      const res = await fetch(`${API_BASE}/shorten`, {
        method: "POST",
        headers: { 
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`
        },
        body: JSON.stringify(payload)
      })
      const respData = await res.json()
      
      if (respData.success) {
        toast.success("Link successfully shortened!")
        setLongUrl('')
        setCustomAlias('')
        fetchDashboard()
      } else {
        toast.error(respData.message || respData.detail || "Failed to shorten link")
      }
    } catch (err) {
      toast.error("Network error")
    } finally {
      setIsShortening(false)
    }
  }

  const copyToClipboard = (text: string) => {
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text)
        .then(() => toast.success("Copied to clipboard"))
        .catch(() => toast.error("Failed to copy link"))
    } else {
      const textArea = document.createElement("textarea")
      textArea.value = text
      textArea.style.position = "fixed"
      textArea.style.left = "-999999px"
      textArea.style.top = "-999999px"
      document.body.appendChild(textArea)
      textArea.focus()
      textArea.select()
      try {
        document.execCommand('copy')
        toast.success("Copied to clipboard")
      } catch (err) {
        toast.error("Failed to copy link")
      }
      textArea.remove()
    }
  }

  const filteredHistory = history.filter(h => 
    h["Short ID"].includes(search) || h["Long URL"].toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className="container mx-auto max-w-6xl px-4 py-12 flex-1">
      <div className="mb-10">
        <h1 className="text-3xl font-bold tracking-tight">Overview</h1>
        <p className="text-muted-foreground mt-1">Manage your links and monitor analytics.</p>
      </div>

      <div className="grid md:grid-cols-2 gap-6 mb-10">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Total Network Clicks</CardDescription>
            <CardTitle className="text-4xl">{stats.clicks}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Active Links</CardDescription>
            <CardTitle className="text-4xl">{stats.links}</CardTitle>
          </CardHeader>
        </Card>
      </div>

      <Card className="mb-10 shadow-md border-primary/20 bg-primary/5">
        <CardHeader>
          <CardTitle>Create New Link</CardTitle>
          <CardDescription>Enter a long URL to generate a secure, trackable short link.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleShorten} className="flex flex-col md:flex-row gap-4">
            <Input 
              required 
              type="url" 
              placeholder="https://very-long-url.com/xyz" 
              className="flex-[2] bg-background"
              value={longUrl}
              onChange={e => setLongUrl(e.target.value)}
            />
            <Input 
              placeholder="Custom alias (optional)" 
              className="flex-1 bg-background"
              value={customAlias}
              onChange={e => setCustomAlias(e.target.value)}
            />
            <Button type="submit" disabled={isShortening} className="md:w-32">
              {isShortening ? "Creating..." : "Shorten"}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4">
          <div>
            <CardTitle>Link History</CardTitle>
            <CardDescription>A complete log of your generated URLs.</CardDescription>
          </div>
          <div className="relative w-full sm:w-64">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input 
              placeholder="Search links..." 
              className="pl-9"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="text-xs uppercase text-muted-foreground bg-muted/50 border-y border-border">
                <tr>
                  <th className="px-6 py-3 font-medium">Short Link</th>
                  <th className="px-6 py-3 font-medium">Original Destination</th>
                  <th className="px-6 py-3 font-medium text-right">Clicks</th>
                  <th className="px-6 py-3 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {filteredHistory.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-6 py-12 text-center text-muted-foreground">
                      No links found. Create one above!
                    </td>
                  </tr>
                ) : (
                  filteredHistory.map((link, i) => {
                    const shortUrl = `${window.location.origin}/${link["Short ID"]}`
                    return (
                      <tr key={i} className="hover:bg-muted/30 transition-colors">
                        <td className="px-6 py-4 font-medium">
                          <a href={shortUrl} target="_blank" rel="noreferrer" className="text-primary hover:underline flex items-center gap-1">
                            {link["Short ID"]} <ExternalLink className="h-3 w-3" />
                          </a>
                        </td>
                        <td className="px-6 py-4 text-muted-foreground max-w-[200px] sm:max-w-xs truncate" title={link["Long URL"]}>
                          {link["Long URL"]}
                        </td>
                        <td className="px-6 py-4 text-right font-medium">
                          {link["Total Clicks"]}
                        </td>
                        <td className="px-6 py-4 text-right">
                          <Button variant="ghost" size="icon" onClick={() => copyToClipboard(shortUrl)} title="Copy URL">
                            <Copy className="h-4 w-4 text-muted-foreground" />
                          </Button>
                        </td>
                      </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

function Footer({ setView }: { setView: (v: View) => void }) {
  return (
    <footer className="border-t border-border/50 py-12 mt-auto">
      <div className="container mx-auto max-w-6xl px-4 flex flex-col md:flex-row justify-between items-center gap-4 text-sm text-muted-foreground">
        <div className="flex items-center gap-2">
          <Link className="h-5 w-5" />
          <span className="font-semibold text-foreground">Short.io</span>
          <span>&copy; 2026</span>
        </div>
        <div className="flex flex-wrap justify-center gap-6">
          <button onClick={() => setView('privacy')} className="hover:text-foreground transition-colors cursor-pointer">Privacy Policy</button>
          <button onClick={() => setView('terms')} className="hover:text-foreground transition-colors cursor-pointer">Terms of Service</button>
          <button onClick={() => setView('cookies')} className="hover:text-foreground transition-colors cursor-pointer">Cookie Policy</button>
          <button onClick={() => setView('disclaimer')} className="hover:text-foreground transition-colors cursor-pointer">Disclaimer</button>
          <a href="#" className="hover:text-foreground transition-colors flex items-center gap-1 ml-4">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4"><path d="M15 22v-4a4.8 4.8 0 0 0-1-3.2c3-.3 6-1.5 6-6.5 0-1.4-.5-2.5-1.5-3.4.1-.3.6-1.6-.1-3.4 0 0-1.2-.4-3.9 1.4a12.3 12.3 0 0 0-7 0C6.2 2.7 5 3.1 5 3.1c-.7 1.8-.2 3.1-.1 3.4-1 .9-1.5 2-1.5 3.4 0 5 3 6.2 6 6.5a4.8 4.8 0 0 0-1 3.2v4"/><path d="M9 18c-4.5 1.5-5-2.5-7-3"/></svg> GitHub
          </a>
        </div>
        <div>
          Made by Arihant Gupta
        </div>
      </div>
    </footer>
  )
}

function LockIcon(props: any) {
  return (
    <svg {...props} xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
    </svg>
  )
}
