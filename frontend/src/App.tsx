import { Layout } from './components/Layout'
import { PublicDemoPage } from './features/demo/PublicDemoPage'

function App() {
  const demo = window.location.pathname === '/demo' || import.meta.env.VITE_PUBLIC_LANDING === '1'
  return demo ? <PublicDemoPage /> : <Layout />
}

export default App
