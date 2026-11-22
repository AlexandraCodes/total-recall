import { useEffect, useRef } from "react";
import { CopyButton, Disclaimer, VerdictBadge } from "./components";
import type { Item } from "./types";

export function ItemDetails({ item, onClose }: { item: Item; onClose: () => void }) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    closeRef.current?.focus();
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onClose]);
  const c = item.check;
  return (
    <div className="overlay overlay-right" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <aside className="drawer" role="dialog" aria-modal="true" aria-labelledby="dr-title">
        <div className="drawer-head">
          <h2 id="dr-title">{item.name}</h2>
          <button ref={closeRef} type="button" className="btn btn-ghost btn-sm" onClick={onClose} aria-label="Close details">Close</button>
        </div>
        {item.error && <p className="error-text" role="alert">The last check failed: {item.error}</p>}
        {!c && <p className="muted">No completed check yet.</p>}
        {c && (
          <>
            <div className="verdict-line"><VerdictBadge verdict={c.verdict} /> <span>{c.headline}</span></div>
            {c.safety_note && <><h3>Safety note</h3><p>{c.safety_note}</p></>}

            {c.official_actions.length > 0 && (
              <>
                <h3>Official actions</h3>
                {c.official_actions.map((a, i) => (
                  <div className="fact" key={i}>
                    <div className="fact-tags">
                      <span className={`tag tag-${a.type}`}>{a.type === "recall" ? "RECALL" : "CPSC WARNING"}</span>
                      {a.match === "possible" && <span className="tag tag-possible">POSSIBLE MATCH</span>}
                      {a.date && <span className="muted">{a.date}</span>}
                    </div>
                    <strong>{a.title}</strong>
                    {a.hazard && <p><b>Hazard:</b> {a.hazard}</p>}
                    {a.remedy && <p><b>Remedy:</b> {a.remedy}</p>}
                    <a className="source-chip" href={a.url} target="_blank" rel="noopener noreferrer">{a.source_title || "Official source"}</a>
                  </div>
                ))}
              </>
            )}

            {c.allegations.length > 0 && (
              <>
                <h3>Reported, unverified</h3>
                {c.allegations.map((a, i) => (
                  <div className="fact" key={i}>
                    <div className="fact-tags"><span className="tag tag-allegation">ALLEGATION</span><span className="muted">{a.kind}</span></div>
                    <p>{a.text}</p>
                    <a className="source-chip" href={a.url} target="_blank" rel="noopener noreferrer">{a.source_title}</a>
                  </div>
                ))}
              </>
            )}

            {c.what_to_do.length > 0 && (
              <><h3>What to do</h3><ul className="plain-list">{c.what_to_do.map((w, i) => <li key={i}>{w}</li>)}</ul></>
            )}

            {c.gaps.length > 0 && (
              <><h3>Gaps in this check</h3><ul className="plain-list gaps">{c.gaps.map((g, i) => <li key={i}>{g}</li>)}</ul></>
            )}

            {c.sources.length > 0 && (
              <>
                <h3>Sources</h3>
                <div className="source-row">
                  {c.sources.map((s) => (
                    <a key={s.url} className="source-chip" href={s.url} target="_blank" rel="noopener noreferrer">{s.title}</a>
                  ))}
                </div>
              </>
            )}
            <p className="muted">Checked {c.checked_on}</p>
          </>
        )}

        {item.drafts.length > 0 && (
          <>
            <h3>Drafts</h3>
            {item.drafts.map((d) => (
              <div className="fact" key={d.id}>
                <div className="fact-tags"><span className="tag">{d.kind === "review_post" ? "REVIEW POST" : "SPONSOR PITCH"}</span></div>
                {d.kind === "review_post" ? (
                  <>
                    <p className="prewrap">{d.caption}</p>
                    {d.story_script.length > 0 && <ol className="plain-list">{d.story_script.map((l, i) => <li key={i}>{l}</li>)}</ol>}
                    <CopyButton text={d.caption} label="Copy caption" />
                  </>
                ) : (
                  <>
                    <p><b>Subject:</b> {d.subject}</p>
                    <p className="prewrap">{d.body}</p>
                    <CopyButton text={`Subject: ${d.subject}\n\n${d.body}`} label="Copy email" />
                  </>
                )}
              </div>
            ))}
          </>
        )}
        <Disclaimer />
      </aside>
    </div>
  );
}
