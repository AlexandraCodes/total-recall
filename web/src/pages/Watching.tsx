import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { isActive } from "../chips";
import { CopyButton, VerdictBadge } from "../components";
import { ItemDetails } from "../ItemDetails";
import { useStore } from "../store";
import type { Item } from "../types";

function AddLinkPost({ item }: { item: Item }) {
  const { act } = useStore();
  const [label, setLabel] = useState("");
  const [url, setUrl] = useState("");
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!label.trim()) return;
    const ok = await act(() => api.addLinkPost(item.id, { label: label.trim(), url: url.trim() || undefined }));
    if (ok) { setLabel(""); setUrl(""); }
  };
  return (
    <form className="add-post" onSubmit={(e) => void submit(e)}>
      <label className="sr-only" htmlFor={`lp-l-${item.id}`}>Post name</label>
      <input id={`lp-l-${item.id}`} placeholder="Post name, e.g. Nursery tour reel" value={label} onChange={(e) => setLabel(e.target.value)} maxLength={120} />
      <label className="sr-only" htmlFor={`lp-u-${item.id}`}>Post link (optional)</label>
      <input id={`lp-u-${item.id}`} placeholder="Post link (optional)" value={url} onChange={(e) => setUrl(e.target.value)} />
      <button type="submit" className="btn btn-ghost btn-sm" disabled={!label.trim()}>Add post</button>
    </form>
  );
}

function AlertCard({ item, onDetails }: { item: Item; onDetails: () => void }) {
  const { act } = useStore();
  const alert = item.alert!;
  const c = item.check;
  const lead = c?.official_actions[0];
  const fu = alert.follow_up;
  return (
    <li className="card alert-card" aria-label={alert.headline}>
      <div className="item-top">
        <h3>{alert.headline}</h3>
        <VerdictBadge verdict={alert.verdict} />
      </div>
      {lead && (
        <dl className="facts">
          <div><dt>Action</dt><dd>{lead.type === "recall" ? "Recall" : "CPSC warning"}{lead.date ? `, ${lead.date}` : ""}{lead.match === "possible" ? " (possible match)" : ""}</dd></div>
          {lead.hazard && <div><dt>Hazard</dt><dd>{lead.hazard}</dd></div>}
          {lead.remedy && <div><dt>Remedy</dt><dd>{lead.remedy}</dd></div>}
          <div><dt>Official source</dt><dd><a href={lead.url} target="_blank" rel="noopener noreferrer">{lead.source_title || lead.url}</a></dd></div>
        </dl>
      )}
      {!lead && c?.allegations[0] && <p className="muted">Based on reported, unverified claims. <button type="button" className="link-btn" onClick={onDetails}>See details</button></p>}

      <h4>Where you linked it</h4>
      {item.link_posts.length === 0 && <p className="muted">Add the posts that link this product so you can track the cleanup.</p>}
      <ul className="post-list">
        {item.link_posts.map((p) => (
          <li key={p.id}>
            <label className="check">
              <input type="checkbox" checked={p.link_removed} onChange={(e) => void act(() => api.patchLinkPost(p.id, { link_removed: e.target.checked }))} />
              <span>{p.url ? <a href={p.url} target="_blank" rel="noopener noreferrer">{p.label}</a> : p.label} <span className="muted">Link removed</span></span>
            </label>
            <button type="button" className="link-btn" onClick={() => void act(() => api.deleteLinkPost(p.id))} aria-label={`Remove ${p.label} from the list`}>Remove</button>
          </li>
        ))}
      </ul>
      <AddLinkPost item={item} />

      <h4>Follow-up draft for your followers</h4>
      {alert.follow_up_status === "generating" && <p className="muted" role="status">Drafting...</p>}
      {alert.follow_up_status === "failed" && (
        <p className="error-text" role="alert">Couldn't draft the follow-up. <button type="button" className="link-btn" onClick={() => void act(() => api.followUp(alert.id))}>Retry</button></p>
      )}
      {fu && (
        <div className="draft-panel">
          <p className="prewrap">{fu.post_caption}</p>
          <CopyButton text={fu.post_caption} label="Copy caption" />
          {fu.story_script.length > 0 && (
            <><h5>Story script</h5><ol className="plain-list">{fu.story_script.map((l, i) => <li key={i}>{l}</li>)}</ol><CopyButton text={fu.story_script.join("\n")} label="Copy script" /></>
          )}
          {fu.comment_reply && (
            <><h5>Reply to a worried comment</h5><p>{fu.comment_reply}</p><CopyButton text={fu.comment_reply} label="Copy reply" /></>
          )}
          <p className="muted">Review before posting. Check the facts against the official source.</p>
        </div>
      )}
      <div className="item-actions">
        <button type="button" className="btn btn-ghost" onClick={onDetails}>Details</button>
        <button type="button" className="btn btn-primary" onClick={() => void act(() => api.handled(alert.id))}>Mark as handled</button>
      </div>
    </li>
  );
}

export default function WatchingPage() {
  const { items, watchRun, loaded, recheck } = useStore();
  const [openId, setOpenId] = useState<number | null>(null);
  const [running, setRunning] = useState(false);
  const watching = items.filter((i) => i.posts_count > 0);
  const flagged = watching.filter((i) => i.alert && !i.alert.handled_at);
  const rest = watching.filter((i) => !(i.alert && !i.alert.handled_at));
  const clean = rest.filter((i) => i.check?.verdict === "no_issues_found" && !isActive(i));
  const handled = rest.filter((i) => i.check && (i.check.verdict === "caution" || i.check.verdict === "do_not_recommend"));
  const incomplete = rest.filter((i) => !clean.includes(i) && !handled.includes(i));
  const open = items.find((i) => i.id === openId) ?? null;

  const run = async () => { setRunning(true); await watchRun(); setRunning(false); };

  return (
    <section aria-labelledby="h-watch">
      <div className="page-head">
        <h1 id="h-watch">Watching</h1>
        <button type="button" className="btn btn-primary" onClick={() => void run()} disabled={running || watching.length === 0}>
          {running ? "Starting..." : "Check everything now"}
        </button>
      </div>
      {loaded && watching.length === 0 && (
        <div className="empty card">
          <p>You're not watching anything yet. Set how many posts a product is linked in, and we'll keep checking it for you.</p>
          <Link to="/list" className="btn btn-primary">Go to my list</Link>
        </div>
      )}
      {flagged.length > 0 && (
        <div className="banner banner-danger" role="alert">
          {flagged.length} product{flagged.length === 1 ? "" : "s"} you've linked {flagged.length === 1 ? "has" : "have"} safety flags
        </div>
      )}
      <ul className="cards">
        {flagged.map((i) => <AlertCard key={i.id} item={i} onDetails={() => setOpenId(i.id)} />)}
      </ul>

      {clean.length > 0 && (
        <p className="summary-line">{clean.length} other linked product{clean.length === 1 ? "" : "s"}: no recalls or warnings found. Not a guarantee of safety.
          {" "}<span className="muted">({clean.map((i) => i.name).join(", ")})</span></p>
      )}
      {handled.length > 0 && <p className="summary-line">{handled.length} flagged product{handled.length === 1 ? "" : "s"} marked as handled: {handled.map((i) => i.name).join(", ")}.</p>}
      {incomplete.length > 0 && (
        <div className="summary-line">
          <p>{incomplete.length} linked product{incomplete.length === 1 ? "" : "s"} without a complete check yet:</p>
          <ul className="plain-list">
            {incomplete.map((i) => (
              <li key={i.id}>{i.name} {isActive(i) ? <span className="muted">checking...</span> : <button type="button" className="link-btn" onClick={() => void recheck(i.id)}>Retry check</button>}</li>
            ))}
          </ul>
        </div>
      )}
      {open && <ItemDetails item={open} onClose={() => setOpenId(null)} />}
    </section>
  );
}
