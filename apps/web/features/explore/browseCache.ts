// Session-only catalog snapshots. No raw statewide map data or persistent storage.
export const BROWSE_FRESH_MS = 60_000;
export const BROWSE_MAX_AGE_MS = 300_000;
export function browseKey(path: string, query = ""): string {
  const params = new URLSearchParams(query);
  params.sort();
  return `${path}${params.size ? `?${params}` : ""}`;
}
type Entry = { data: unknown; saved: number; bytes: number; prefetched: boolean };
type Flight = { controller: AbortController; promise: Promise<unknown>; users: number; prefetched: boolean };
type Options = { now?: () => number; entries?: number; bytes?: number; fresh?: number; maxAge?: number };
const abortError = () => new DOMException("Request no longer needed", "AbortError");

export class BrowseCache {
  private entries = new Map<string, Entry>();
  private flights = new Map<string, Flight>();
  private totalBytes = 0;
  private speculative = 0;
  private revision: string | undefined;
  private version = 0;
  private listeners = new Set<() => void>();
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  generation = () => this.version;
  observeRevision(revision: string) {
    if(this.revision===undefined){this.revision=revision;return;}
    this.invalidate(revision);
  }
  private now: () => number;
  private bounds: Required<Omit<Options, "now">>;
  readonly metrics = { hits: 0, misses: 0, deduplicated: 0, prefetchHits: 0, prefetches: 0, evictions: 0 };
  constructor(options: Options = {}) {
    this.now = options.now ?? Date.now;
    this.bounds = { entries: options.entries ?? 64, bytes: options.bytes ?? 4 * 1024 * 1024, fresh: options.fresh ?? BROWSE_FRESH_MS, maxAge: options.maxAge ?? BROWSE_MAX_AGE_MS };
  }
  snapshot<T>(key: string): { data: T; saved: number; fresh: boolean } | undefined {
    const entry = this.entries.get(key);
    if (!entry) return;
    if (this.now() - entry.saved >= this.bounds.maxAge) { this.remove(key); return; }
    return { data: entry.data as T, saved: entry.saved, fresh: this.now() - entry.saved < this.bounds.fresh };
  }
  private remove(key: string) { const entry=this.entries.get(key); if(entry) this.totalBytes-=entry.bytes; this.entries.delete(key); }
  invalidate(revision?: string) {
    if (revision !== undefined && this.revision === revision) return;
    this.revision = revision;
    this.entries.clear(); this.totalBytes = 0;
    for (const flight of this.flights.values()) flight.controller.abort();
    this.flights.clear();
    this.version++;
    for(const listener of this.listeners)listener();
  }
  inspect() { return { entries:this.entries.size, bytes:this.totalBytes, flights:this.flights.size, speculative:this.speculative }; }
  load<T>(key: string, loader: (signal: AbortSignal) => Promise<T>, signal?: AbortSignal, force = false, speculative = false): Promise<T> {
    if (signal?.aborted) return Promise.reject(abortError());
    const snapshot = this.snapshot<T>(key);
    if (!force && snapshot?.fresh) {
      const entry = this.entries.get(key)!;
      this.entries.delete(key); this.entries.set(key,entry);
      if (!speculative) { this.metrics.hits++; if(entry.prefetched){this.metrics.prefetchHits++;entry.prefetched=false;} }
      return Promise.resolve(snapshot.data);
    }
    let flight = this.flights.get(key);
    if (flight) this.metrics.deduplicated++;
    else {
      this.metrics.misses++;
      const controller = new AbortController();
      flight = { controller, users:0, prefetched:speculative, promise:Promise.resolve() };
      const created = flight;
      this.flights.set(key,created);
      created.promise = Promise.resolve().then(() => loader(controller.signal)).then(data => {
        if(controller.signal.aborted || this.flights.get(key)!==created)throw abortError();
        if (!controller.signal.aborted && this.flights.get(key)===created) {
          const bytes = new TextEncoder().encode(JSON.stringify(data)).byteLength;
          if(bytes<=this.bounds.bytes){
            this.remove(key);
            this.entries.set(key,{data,saved:this.now(),bytes,prefetched:created.prefetched});
            this.totalBytes+=bytes;
            while(this.entries.size>this.bounds.entries || this.totalBytes>this.bounds.bytes){this.remove(this.entries.keys().next().value!);this.metrics.evictions++;}
          }
        }
        return data;
      }).finally(() => { if(this.flights.get(key)===created)this.flights.delete(key); });
    }
    const shared = flight;
    shared.users++;
    return new Promise<T>((resolve,reject) => {
      let done=false;
      const release = () => {
        if(done)return; done=true; signal?.removeEventListener("abort",cancel);
        shared.users--;
        if(!shared.users && this.flights.get(key)===shared){shared.controller.abort();this.flights.delete(key);}
      };
      const cancel = () => { release(); reject(abortError()); };
      signal?.addEventListener("abort",cancel,{once:true});
      shared.promise.then(data=>{if(!done){release();resolve(data as T);}},error=>{if(!done){release();reject(error);}});
    });
  }
  prefetch<T>(key: string, loader: (signal: AbortSignal) => Promise<T>) {
    if(this.snapshot(key)?.fresh || this.flights.has(key) || this.speculative>=2)return;
    this.speculative++; this.metrics.prefetches++;
    void this.load(key,loader,undefined,false,true).catch(()=>{ /* Foreground consumers report recoverable failures. */ }).finally(()=>{this.speculative--;});
  }
}
export const browseCache = new BrowseCache();
// Enabled only in the owned benchmark build. No logging or production debug surface.
if(typeof window!=="undefined" && process.env.NEXT_PUBLIC_BROWSING_METRICS==="1"){
  Object.assign(window,{paleoBrowseMetrics:()=>({...browseCache.metrics,...browseCache.inspect()})});
}
