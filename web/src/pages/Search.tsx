import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, ApiException } from "../api";
import { chipsFor } from "../chips";
import { StatusChips } from "../components";
import { useStore } from "../store";
import type { Mode, ProductResult } from "../types";

const MODES: { id: Mode; label: string }[] = [
  { id: "review", label: "I want to review it" },
  { id: "sponsored", label: "I want the brand to sponsor me" },
];

export default function SearchPage() {
  const { items, addItem, defaultMode, setDefaultMode, drafting } = useStore();
  const [q, setQ] = useState("");
  const [asked, setAsked] = useState("");
  const [results, setResults] = useState<ProductResult[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const term = q.trim();
    if (term.length < 2) return;
    setBusy(true);
    setError(null);
    setAsked(term);
    try {
      setResults((await api.search(term)).results);
    } catch (err) {
      setResults([]);
      setError(err instanceof ApiException ? err.message : "Search failed. You can still add the product as typed.");
    } finally {
      setBusy(false);
    }
  };

  const inList = (name: string) => items.some((i) => i.name.toLowerCase() === name.toLowerCase());

  const add = async (r: ProductResult) => {
    setAdding(r.id);
    await addItem({ name: r.name, brand: r.brand || undefined, url: r.url || undefined, retailer: r.retailer || undefined, image_url: r.image_url || undefined });
    setAdding(null);
  };

  return (
    <div className="two-col">
      <section aria-labelledby="h-search">
        <h1 id="h-search">Search any product. We check it before you post.</h1>
        <div className="seg" role="radiogroup" aria-label="What do you want to do with the product?">
          {MODES.map((m) => (
            <button key={m.id} type="button" role="radio" aria-checked={defaultMode === m.id}
              className={defaultMode === m.id ? "seg-btn on" : "seg-btn"} onClick={() => setDefaultMode(m.id)}>{m.label}</button>
          ))}
        </div>
        <ul className="trust-chips">
          <li>CPSC recalls</li><li>CPSC warnings</li><li>Lawsuits, labeled as allegations</li><li>Every claim cited</li>
        </ul>
        <form className="search-form" onSubmit={(e) => void submit(e)} role="search">
          <label className="sr-only" htmlFor="q">Product name, brand, or link</label>
          <input id="q" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Try: bassinet, a product name, or paste a link" maxLength={200} />
          <button type="submit" className="btn btn-primary" disabled={busy || q.trim().length < 2}>{busy ? "Searching..." : "Search"}</button>
        </form>

        {error && <p className="error-text" role="alert">{error}</p>}
        {busy && <div className="skeleton-list" aria-hidden="true"><div className="skeleton" /><div className="skeleton" /><div className="skeleton" /></div>}

        {results && !busy && (
          <ul className="results">
            {results.map((r) => {
              const added = inList(r.name);
              return (
                <li className={r.pre_flag ? "result result-flag" : "result"} key={r.id}>
                  <div className="thumb" aria-hidden="true">{r.image_url ? <img src={r.image_url} alt="" loading="lazy" /> : r.name.slice(0, 1)}</div>
                  <div className="result-main">
                    <strong>{r.name}</strong>
                    <span className="muted">{[r.brand, r.retailer, r.price_text].filter(Boolean).join(" · ")}</span>
                    {r.pre_flag && (
                      <a className="chip-flag" href={r.pre_flag.url} target="_blank" rel="noopener noreferrer">
                        CPSC recall on file, {r.pre_flag.date}
                      </a>
                    )}
                  </div>
                  <button type="button" className={r.pre_flag ? "btn btn-danger-outline" : "btn btn-primary"} disabled={added || adding === r.id}
                    onClick={() => void add(r)}>
                    {added ? "Added" : r.pre_flag ? "Add anyway" : "Add to list"}
                  </button>
                </li>
              );
            })}
            <li className="result result-typed">
              <div className="result-main"><strong>Add "{asked}" as typed</strong><span className="muted">Skips search results. We still run the full check.</span></div>
              <button type="button" className="btn btn-ghost" disabled={inList(asked) || adding === "typed"} onClick={() => {
                setAdding("typed");
                void addItem({ name: asked }).finally(() => setAdding(null));
              }}>{inList(asked) ? "Added" : "Add"}</button>
            </li>
          </ul>
        )}
      </section>

      <aside className="side-card" aria-labelledby="h-list">
        <h2 id="h-list">Your list</h2>
        {items.length === 0 && <p className="muted">Nothing here yet. Add a product and its safety check starts right away.</p>}
        <ul className="mini-list">
          {items.slice(0, 8).map((i) => (
            <li key={i.id}>
              <strong>{i.name}</strong>
              <StatusChips chips={chipsFor(i, drafting.has(i.id))} />
            </li>
          ))}
        </ul>
        {items.length > 0 && <Link to="/list" className="btn btn-ghost btn-block">Open my list</Link>}
        <Link to="/watching" className="btn btn-primary btn-block">Watch these products after I post</Link>
      </aside>
    </div>
  );
}
