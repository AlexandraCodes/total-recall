import { useEffect, useRef, useState, type FormEvent } from "react";
import { NavLink } from "react-router-dom";
import { api } from "./api";
import { VERDICT_LABEL, type Chip } from "./chips";
import { useStore } from "./store";
import type { Profile, Verdict } from "./types";

export function VerdictBadge({ verdict }: { verdict: Verdict }) {
  return <span className={`badge badge-${verdict}`}>{VERDICT_LABEL[verdict]}</span>;
}

export function StatusChips({ chips }: { chips: Chip[] }) {
  return (
    <ul className="chips" aria-label="Progress">
      {chips.map((c) => (
        <li key={c.label} className={`chip chip-${c.state}`}>
          <span className="chip-label">{c.label}</span>
          <span className="chip-state">{c.text}</span>
        </li>
      ))}
    </ul>
  );
}

export function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [done, setDone] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
    }
    setDone(true);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setDone(false), 1600);
  };
  return (
    <button type="button" className="btn btn-ghost btn-sm" onClick={() => void copy()} aria-live="polite">
      {done ? "Copied" : label}
    </button>
  );
}

export function Disclaimer() {
  return (
    <p className="disclaimer">
      Informational only. Recalls and warnings come from CPSC and other cited sources; lawsuits and complaints are allegations,
      not findings. Always confirm on CPSC.gov. "No recalls or warnings found" is not a guarantee of safety.
    </p>
  );
}

export function DemoBanner() {
  const { health } = useStore();
  if (!health || health.mode === "live") return null;
  return (
    <div className="banner banner-demo" role="status">
      {health.mode === "demo-cached"
        ? "Replaying a saved live run. Not a live check."
        : "Demo mode: sample data, not a live check. Recall details come from public CPSC notices but were not fetched live."}
    </div>
  );
}

export function Notice() {
  const { notice, clearNotice, offline } = useStore();
  return (
    <div aria-live="polite">
      {offline && <div className="banner banner-danger" role="alert">Connection lost. Retrying...</div>}
      {notice && (
        <div className="banner banner-notice" role="status">
          <span>{notice}</span>
          <button type="button" className="btn btn-ghost btn-sm" onClick={clearNotice}>Dismiss</button>
        </div>
      )}
    </div>
  );
}

export function Header({ onProfile }: { onProfile: () => void }) {
  const { openAlerts, profile } = useStore();
  const initial = (profile?.handle || "Me").replace("@", "").slice(0, 1).toUpperCase();
  return (
    <header className="header">
      <div className="header-inner">
        <NavLink to="/" className="logo" aria-label="Recall Watch home">
          <span className="logo-mark" aria-hidden="true">R</span>
          <span>Recall Watch</span>
        </NavLink>
        <nav aria-label="Main">
          <NavLink to="/" end>Search</NavLink>
          <NavLink to="/list">My list</NavLink>
          <NavLink to="/watching">
            Watching
            {openAlerts > 0 && <span className="nav-badge" aria-label={`${openAlerts} open alerts`}>{openAlerts}</span>}
          </NavLink>
        </nav>
        <button type="button" className="avatar" onClick={onProfile} aria-label="Creator profile">{initial}</button>
      </div>
    </header>
  );
}

export function DemoTools() {
  const { health, refreshHealth, act, refresh } = useStore();
  if (!health) return null;
  const demoOn = health.mode !== "live";
  const toggle = async () => {
    await act(() => api.demoMode(!demoOn));
    await refreshHealth();
    await refresh();
  };
  return (
    <details className="demo-tools">
      <summary>Demo tools</summary>
      <div className="demo-tools-body">
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => void act(() => api.demoSeed())}>Load demo list</button>
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => void act(() => api.demoReset())}>Clear everything</button>
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => void toggle()}
          disabled={demoOn && !health.live_ready} title={demoOn && !health.live_ready ? "API keys are not set" : undefined}>
          {demoOn ? "Switch to live mode" : "Switch to demo data"}
        </button>
      </div>
    </details>
  );
}

export function ProfileModal({ onClose }: { onClose: () => void }) {
  const { profile, saveProfile } = useStore();
  const [form, setForm] = useState<Profile>(profile ?? { handle: "", platform: "instagram", niche: "", followers: 0, engagement: null });
  const [busy, setBusy] = useState(false);
  const first = useRef<HTMLInputElement>(null);
  useEffect(() => {
    first.current?.focus();
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onClose]);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    const ok = await saveProfile({ ...form, handle: form.handle?.trim() || null });
    setBusy(false);
    if (ok) onClose();
  };
  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <form className="modal" role="dialog" aria-modal="true" aria-labelledby="pf-title" onSubmit={(e) => void submit(e)}>
        <h2 id="pf-title">Your creator profile</h2>
        <p className="muted">Used to write sponsor pitches and review posts. Stored on this server only.</p>
        <label>Handle (optional)
          <input ref={first} value={form.handle ?? ""} onChange={(e) => setForm({ ...form, handle: e.target.value })} maxLength={60} placeholder="@yourhandle" />
        </label>
        <label>Main platform
          <select value={form.platform} onChange={(e) => setForm({ ...form, platform: e.target.value })}>
            {["instagram", "tiktok", "youtube", "facebook", "pinterest", "blog"].map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </label>
        <label>Niche
          <input value={form.niche} onChange={(e) => setForm({ ...form, niche: e.target.value })} maxLength={120} placeholder="e.g. newborn essentials" />
        </label>
        <div className="row">
          <label>Followers
            <input type="number" min={0} value={form.followers} onChange={(e) => setForm({ ...form, followers: Math.max(0, Number(e.target.value) || 0) })} />
          </label>
          <label>Engagement % (optional)
            <input type="number" min={0} max={100} step="0.1" value={form.engagement ?? ""}
              onChange={(e) => setForm({ ...form, engagement: e.target.value === "" ? null : Math.min(100, Math.max(0, Number(e.target.value))) })} />
          </label>
        </div>
        <div className="row row-end">
          <button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={busy}>{busy ? "Saving..." : "Save"}</button>
        </div>
      </form>
    </div>
  );
}
