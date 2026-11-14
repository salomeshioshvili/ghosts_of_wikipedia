import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { Article } from './pages/Article'
import { Home } from './pages/Home'
import { Search } from './pages/Search'
import { Tombstone } from './pages/Tombstone'

export default function App() {
  return (
    <BrowserRouter>
      <div className="app-shell">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/article/:pageId" element={<Article />} />
          <Route path="/search" element={<Search />} />
          <Route path="/tombstone/:pageId/:hash" element={<Tombstone />} />
        </Routes>
      </div>
    </BrowserRouter>
  )
}
