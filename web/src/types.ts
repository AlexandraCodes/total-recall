// Mirrors PRD section 8. The API returns exactly these shapes (snake_case keys).
export type Verdict = "do_not_recommend" | "caution" | "no_issues_found" | "unverified";
export type Phase = "queued" | "checking" | "done" | "error";
export type Mode = "review" | "sponsored";
export type MatchLevel = "confirmed" | "possible";
export type JobStatus = "generating" | "done" | "failed";

export interface SourceRef { url: string; title: string }
export interface OfficialAction {
  type: "recall" | "warning"; title: string; date: string | null; hazard: string;
  remedy: string | null; match: MatchLevel; url: string; source_title: string;
}
export interface Allegation { kind: "lawsuit" | "complaint" | "report"; text: string; url: string; source_title: string }
export interface CheckResult {
  verdict: Verdict; headline: string; safety_note: string; what_to_do: string[];
  official_actions: OfficialAction[]; allegations: Allegation[];
  sources: SourceRef[]; gaps: string[]; checked_on: string;
}
export interface PreFlag { recall_number: string | null; date: string; title: string; url: string }
export interface ProductResult {
  id: string; name: string; brand: string; retailer: string | null; price_text: string | null;
  url: string | null; image_url: string | null; pre_flag: PreFlag | null;
}
export interface LinkPost { id: number; label: string; url: string | null; posted_on: string | null; link_removed: boolean }
export interface FollowUp { post_caption: string; story_script: string[]; comment_reply: string }
export interface Alert {
  id: number; item_id: number; verdict: Verdict; headline: string;
  follow_up: FollowUp | null; follow_up_status: JobStatus; created_at: string; handled_at: string | null;
}
export type DraftContent =
  | { kind: "review_post"; caption: string; story_script: string[] }
  | { kind: "sponsor_pitch"; subject: string; body: string; partnership_page_url: string | null };
export type Draft = DraftContent & { id: number; status: JobStatus; created_at: string };
export interface Item {
  id: number; name: string; brand: string | null; product: string | null; model: string | null;
  url: string | null; image_url: string | null; retailer: string | null;
  mode: Mode; posts_count: number; phase: Phase; error: string | null;
  check: CheckResult | null; link_posts: LinkPost[]; alert: Alert | null; drafts: Draft[];
}
export interface Profile { handle: string | null; platform: string; niche: string; followers: number; engagement: number | null }
export interface HealthInfo { live_ready: boolean; model: string; mode: "live" | "demo-cached" | "demo-sample"; cpsc_index_size: number }
export interface ApiErrorBody { error: { code: string; message: string } }

export interface NewItem {
  name: string; brand?: string; url?: string; retailer?: string; image_url?: string; mode?: Mode;
}
