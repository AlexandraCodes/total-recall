import type { Item, Verdict } from "./types";

export type ChipState = "waiting" | "running" | "done" | "blocked" | "error" | "idle";
export interface Chip { label: string; state: ChipState; text: string }

export const VERDICT_LABEL: Record<Verdict, string> = {
  do_not_recommend: "Do not recommend",
  caution: "Use caution",
  no_issues_found: "No recalls or warnings found",
  unverified: "Couldn't complete the check",
};

const TEXT: Record<ChipState, string> = {
  waiting: "Waiting", running: "Running", done: "Done", blocked: "Blocked", error: "Error", idle: "Not started",
};

/** PRD F3 chip mapping. While re-checking, the previous check stays visible, so Safety note stays "done". */
export function chipsFor(item: Item, drafting: boolean): Chip[] {
  const recall: ChipState =
    item.phase === "queued" ? "waiting" : item.phase === "checking" ? "running" : item.phase === "error" ? "error" : "done";
  let note: ChipState = "waiting";
  if (item.check) note = "done";
  else if (item.phase === "checking") note = "running";
  else if (item.phase === "error") note = "error";
  let drafts: ChipState = "waiting";
  if (item.check?.verdict === "do_not_recommend") drafts = "blocked";
  else if (drafting) drafts = "running";
  else if (item.drafts.length > 0) drafts = "done";
  else if (item.check) drafts = "idle";
  return [
    { label: "Recall check", state: recall, text: TEXT[recall] },
    { label: "Safety note", state: note, text: TEXT[note] },
    { label: "Drafts", state: drafts, text: TEXT[drafts] },
  ];
}

export const isActive = (i: Item) => i.phase === "queued" || i.phase === "checking";
