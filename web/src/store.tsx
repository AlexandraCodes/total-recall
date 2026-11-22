import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, ApiException } from "./api";
import { isActive } from "./chips";
import type { HealthInfo, Item, Mode, NewItem, Profile } from "./types";

interface Store {
  items: Item[];
  loaded: boolean;
  offline: boolean;
  health: HealthInfo | null;
  profile: Profile | null;
  defaultMode: Mode;
  setDefaultMode: (m: Mode) => void;
  drafting: Set<number>;
  notice: string | null;
  clearNotice: () => void;
  openAlerts: number;
  refresh: () => Promise<void>;
  addItem: (i: NewItem) => Promise<Item | null>;
  patchItem: (id: number, patch: { mode?: Mode; posts_count?: number }) => Promise<void>;
  removeItem: (id: number) => Promise<void>;
  recheck: (id: number) => Promise<void>;
  draft: (id: number, kind: "review_post" | "sponsor_pitch", ack: boolean) => Promise<void>;
  watchRun: () => Promise<void>;
  saveProfile: (p: Profile) => Promise<boolean>;
  refreshHealth: () => Promise<void>;
  /** Run any action that returns an updated Item, merge it into state, and surface errors. */
  act: (fn: () => Promise<Item | unknown>) => Promise<boolean>;
}

const Ctx = createContext<Store | null>(null);

export function useStore(): Store {
  const s = useContext(Ctx);
  if (!s) throw new Error("StoreProvider missing");
  return s;
}

export function StoreProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Item[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [offline, setOffline] = useState(false);
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [defaultMode, setDefaultMode] = useState<Mode>("review");
  const [drafting, setDrafting] = useState<Set<number>>(new Set());
  const [notice, setNotice] = useState<string | null>(null);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; };
  }, []);

  const fail = useCallback((e: unknown) => {
    setNotice(e instanceof ApiException ? e.message : "Something went wrong. Try again.");
  }, []);

  const refresh = useCallback(async () => {
    try {
      const list = await api.items();
      if (!alive.current) return;
      setItems(list);
      setOffline(false);
      setLoaded(true);
    } catch (e) {
      if (!alive.current) return;
      if (e instanceof ApiException && e.code === "network") setOffline(true);
      setLoaded(true);
    }
  }, []);

  const refreshHealth = useCallback(async () => {
    try {
      setHealth(await api.health());
    } catch { /* banner simply stays as it was */ }
  }, []);

  useEffect(() => {
    void refresh();
    void refreshHealth();
    api.getProfile().then(setProfile).catch(() => undefined);
  }, [refresh, refreshHealth]);

  // Poll every 1.5 s while anything is queued/checking or a follow-up is generating; stop when idle.
  const busy = items.some((i) => isActive(i) || i.alert?.follow_up_status === "generating");
  useEffect(() => {
    if (!busy) return;
    const t = setTimeout(() => void refresh(), 1500);
    return () => clearTimeout(t);
  }, [busy, items, refresh]);

  // While offline, retry gently.
  useEffect(() => {
    if (!offline) return;
    const t = setTimeout(() => void refresh(), 3000);
    return () => clearTimeout(t);
  }, [offline, refresh, items]);

  const merge = useCallback((it: Item) => {
    setItems((prev) => (prev.some((p) => p.id === it.id) ? prev.map((p) => (p.id === it.id ? it : p)) : [it, ...prev]));
  }, []);

  const isItem = (x: unknown): x is Item => typeof x === "object" && x !== null && "phase" in x && "posts_count" in x;

  const act = useCallback(async (fn: () => Promise<Item | unknown>) => {
    try {
      const r = await fn();
      if (isItem(r)) merge(r);
      await refresh();
      return true;
    } catch (e) {
      fail(e);
      return false;
    }
  }, [merge, refresh, fail]);

  const addItem = useCallback(async (i: NewItem) => {
    try {
      const it = await api.addItem({ mode: defaultMode, ...i });
      merge(it);
      void refresh();
      return it;
    } catch (e) {
      fail(e);
      return null;
    }
  }, [defaultMode, merge, refresh, fail]);

  const patchItem = useCallback(async (id: number, patch: { mode?: Mode; posts_count?: number }) => {
    await act(() => api.patchItem(id, patch));
  }, [act]);

  const removeItem = useCallback(async (id: number) => {
    if (await act(() => api.deleteItem(id))) setItems((prev) => prev.filter((p) => p.id !== id));
  }, [act]);

  const recheck = useCallback(async (id: number) => { await act(() => api.recheck(id)); }, [act]);

  const draft = useCallback(async (id: number, kind: "review_post" | "sponsor_pitch", ack: boolean) => {
    setDrafting((s) => new Set(s).add(id));
    try {
      await act(() => api.draft(id, kind, ack));
    } finally {
      setDrafting((s) => { const n = new Set(s); n.delete(id); return n; });
    }
  }, [act]);

  const watchRun = useCallback(async () => {
    await act(async () => {
      const r = await api.watchRun();
      if (r.queued === 0) setNotice("Nothing to check yet. Set how many posts a product is linked in first.");
    });
  }, [act]);

  const saveProfile = useCallback(async (p: Profile) => {
    try {
      setProfile(await api.putProfile(p));
      return true;
    } catch (e) {
      fail(e);
      return false;
    }
  }, [fail]);

  const openAlerts = items.filter((i) => i.alert && !i.alert.handled_at).length;

  const value = useMemo<Store>(() => ({
    items, loaded, offline, health, profile, defaultMode, setDefaultMode, drafting, notice,
    clearNotice: () => setNotice(null), openAlerts, refresh, addItem, patchItem, removeItem, recheck, draft,
    watchRun, saveProfile, refreshHealth, act,
  }), [items, loaded, offline, health, profile, defaultMode, drafting, notice, openAlerts, refresh, addItem, patchItem,
    removeItem, recheck, draft, watchRun, saveProfile, refreshHealth, act]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
