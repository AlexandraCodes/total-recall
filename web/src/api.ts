import type {
  ApiErrorBody, HealthInfo, Item, LinkPost, Mode, NewItem, Profile, ProductResult, Alert,
} from "./types";

export class ApiException extends Error {
  code: string;
  status: number;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiException(0, "network", "Connection lost. Check your connection and try again.");
  }
  if (!res.ok) {
    let code = "error";
    let message = `Request failed (${res.status}).`;
    try {
      const j = (await res.json()) as ApiErrorBody;
      code = j.error.code;
      message = j.error.message;
    } catch { /* non-JSON error body */ }
    throw new ApiException(res.status, code, message);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => req<HealthInfo>("GET", "/api/health"),
  getProfile: () => req<Profile>("GET", "/api/profile"),
  putProfile: (p: Profile) => req<Profile>("PUT", "/api/profile", p),
  search: (q: string) => req<{ mode: HealthInfo["mode"]; results: ProductResult[] }>("POST", "/api/products/search", { q }),
  items: () => req<Item[]>("GET", "/api/items"),
  addItem: (i: NewItem) => req<Item>("POST", "/api/items", i),
  patchItem: (id: number, patch: { mode?: Mode; posts_count?: number }) => req<Item>("PATCH", `/api/items/${id}`, patch),
  deleteItem: (id: number) => req<{ ok: boolean }>("DELETE", `/api/items/${id}`),
  recheck: (id: number) => req<Item>("POST", `/api/items/${id}/check`),
  draft: (id: number, kind: "review_post" | "sponsor_pitch", ack: boolean) =>
    req<Item>("POST", `/api/items/${id}/drafts`, { kind, ack }),
  addLinkPost: (id: number, lp: { label: string; url?: string }) => req<Item>("POST", `/api/items/${id}/link-posts`, lp),
  patchLinkPost: (id: number, patch: Partial<Pick<LinkPost, "link_removed" | "label">>) =>
    req<Item>("PATCH", `/api/link-posts/${id}`, patch),
  deleteLinkPost: (id: number) => req<Item>("DELETE", `/api/link-posts/${id}`),
  watchRun: () => req<{ queued: number }>("POST", "/api/watch/run"),
  followUp: (id: number) => req<Alert>("POST", `/api/alerts/${id}/follow-up`),
  handled: (id: number) => req<Alert>("POST", `/api/alerts/${id}/handled`),
  demoSeed: () => req<Item[]>("POST", "/api/demo/seed"),
  demoReset: () => req<{ ok: boolean }>("POST", "/api/demo/reset"),
  demoMode: (on: boolean | null) => req<HealthInfo>("POST", "/api/demo/mode", { on }),
};
