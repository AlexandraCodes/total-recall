import { useState } from "react";
import { Link } from "react-router-dom";
import { chipsFor, isActive } from "../chips";
import { StatusChips, VerdictBadge } from "../components";
import { ItemDetails } from "../ItemDetails";
import { useStore } from "../store";
import type { Item, Mode } from "../types";

function PostsInput({ item }: { item: Item }) {
  const { patchItem } = useStore();
  const [val, setVal] = useState(String(item.posts_count));
  const [prev, setPrev] = useState(item.posts_count);
  if (prev !== item.posts_count) { setPrev(item.posts_count); setVal(String(item.posts_count)); }
  const commit = () => {
    const n = Number(val);
    if (!Number.isInteger(n) || n < 0 || n > 999) { setVal(String(item.posts_count)); return; }
    if (n !== item.posts_count) void patchItem(item.id, { posts_count: n });
  };
  return (
    <label className="inline-field">Linked in
      <input type="number" min={0} max={999} value={val} onChange={(e) => setVal(e.target.value)} onBlur={commit}
        onKeyDown={(e) => e.key === "Enter" && (e.currentTarget as HTMLInputElement).blur()} aria-label={`Posts linking ${item.name}`} />
      posts
    </label>
  );
}

function ItemCard({ item, onDetails }: { item: Item; onDetails: () => void }) {
  const { patchItem, recheck, removeItem, draft, drafting } = useStore();
  const [ack, setAck] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const v = item.check?.verdict;
  const flagged = v === "do_not_recommend";
  const needsAck = v === "caution" || v === "unverified";
  const kind = item.mode === "review" ? "review_post" : "sponsor_pitch";
  const canDraft = !!item.check && !flagged && !isActive(item) && !drafting.has(item.id) && (!needsAck || ack);
  return (
    <li className={flagged ? "card item item-flagged" : "card item"}>
      <div className="item-top">
        <div>
          <h3>{item.name}</h3>
          <p className="muted">{[item.brand, item.retailer].filter(Boolean).join(" · ") || "Brand not identified yet"}</p>
        </div>
        {v && <VerdictBadge verdict={v} />}
      </div>
      <StatusChips chips={chipsFor(item, drafting.has(item.id))} />
      {item.check && <p className="headline">{item.check.headline}</p>}
      {item.error && (
        <p className="error-text" role="alert">
          Check failed. {item.check ? "Showing the previous result. " : ""}
          <button type="button" className="link-btn" onClick={() => void recheck(item.id)}>Retry</button>
        </p>
      )}
      <div className="item-controls">
        <div className="seg seg-sm" role="radiogroup" aria-label={`Mode for ${item.name}`}>
          {(["review", "sponsored"] as Mode[]).map((m) => (
            <button key={m} type="button" role="radio" aria-checked={item.mode === m} className={item.mode === m ? "seg-btn on" : "seg-btn"}
              onClick={() => item.mode !== m && void patchItem(item.id, { mode: m })}>{m === "review" ? "Review" : "Sponsored"}</button>
          ))}
        </div>
        <PostsInput item={item} />
      </div>
      {flagged && <p className="muted">Flagged products don't get a pitch or review script.</p>}
      {needsAck && !isActive(item) && (
        <label className="check"><input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} /> I've read the safety note</label>
      )}
      <div className="item-actions">
        <button type="button" className="btn btn-ghost" onClick={onDetails}>Details</button>
        <button type="button" className="btn btn-ghost" disabled={isActive(item)} onClick={() => void recheck(item.id)}>Re-check</button>
        <button type="button" className="btn btn-primary" disabled={!canDraft} onClick={() => void draft(item.id, kind, ack)}>
          {drafting.has(item.id) ? "Drafting..." : kind === "review_post" ? "Draft review" : "Draft pitch"}
        </button>
        {confirm ? (
          <button type="button" className="btn btn-danger" onClick={() => void removeItem(item.id)} onBlur={() => setConfirm(false)} autoFocus>Confirm remove</button>
        ) : (
          <button type="button" className="btn btn-ghost" onClick={() => setConfirm(true)}>Remove</button>
        )}
      </div>
    </li>
  );
}

export default function ListPage() {
  const { items, loaded } = useStore();
  const [openId, setOpenId] = useState<number | null>(null);
  const open = items.find((i) => i.id === openId) ?? null;
  return (
    <section aria-labelledby="h-list">
      <h1 id="h-list">My list</h1>
      {!loaded && <div className="skeleton-list" aria-hidden="true"><div className="skeleton" /><div className="skeleton" /></div>}
      {loaded && items.length === 0 && (
        <div className="empty card"><p>Your list is empty.</p><Link to="/" className="btn btn-primary">Search for a product</Link></div>
      )}
      <ul className="cards">
        {items.map((i) => <ItemCard key={i.id} item={i} onDetails={() => setOpenId(i.id)} />)}
      </ul>
      {open && <ItemDetails item={open} onClose={() => setOpenId(null)} />}
    </section>
  );
}
