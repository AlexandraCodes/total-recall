import { useState } from "react";
import { Route, Routes } from "react-router-dom";
import { DemoBanner, DemoTools, Disclaimer, Header, Notice, ProfileModal } from "./components";
import ListPage from "./pages/List";
import SearchPage from "./pages/Search";
import WatchingPage from "./pages/Watching";
import { StoreProvider } from "./store";

export default function App() {
  const [profileOpen, setProfileOpen] = useState(false);
  return (
    <StoreProvider>
      <Header onProfile={() => setProfileOpen(true)} />
      <DemoBanner />
      <Notice />
      <main className="container">
        <Routes>
          <Route path="/" element={<SearchPage />} />
          <Route path="/list" element={<ListPage />} />
          <Route path="/watching" element={<WatchingPage />} />
          <Route path="*" element={<SearchPage />} />
        </Routes>
      </main>
      <footer className="container footer">
        <Disclaimer />
        <DemoTools />
      </footer>
      {profileOpen && <ProfileModal onClose={() => setProfileOpen(false)} />}
    </StoreProvider>
  );
}
