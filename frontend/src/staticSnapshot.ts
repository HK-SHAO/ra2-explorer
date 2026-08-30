import type {
  AppInfo,
  Asset,
  AssetAssociationPage,
  AssetMetadata,
  AssetPage,
  EntityPage,
  EntitySummary,
  GameEntity,
  GameLanguage,
  MediaItem,
  MediaPage,
  ReferenceStatus,
  SemanticDiagnostics,
  Source,
  Stats,
  UpdateInfo,
} from "./api";

export const isStaticSnapshot = import.meta.env.VITE_RA2EXP_STATIC_SNAPSHOT === "1";

interface StaticAssetBundle {
  asset: Asset;
  metadata: AssetMetadata;
  associations: Record<GameLanguage, AssetAssociationPage>;
}

interface StaticSnapshotManifest {
  schema_version: 1;
  snapshot_id: string;
  created_at: string;
  app_version: string;
  source: Source;
  stats: Stats;
  diagnostics: SemanticDiagnostics;
  reference_status: ReferenceStatus;
}

const jsonCache = new Map<string, Promise<unknown>>();

function publicUrl(path: string) {
  const base = import.meta.env.BASE_URL.endsWith("/")
    ? import.meta.env.BASE_URL
    : `${import.meta.env.BASE_URL}/`;
  return `${base}${path.replace(/^\/+/, "")}`;
}

function snapshotUrl(path: string) {
  return publicUrl(`data/${path}`);
}

function loadJson<T>(path: string): Promise<T> {
  const url = snapshotUrl(path);
  let pending = jsonCache.get(url) as Promise<T> | undefined;
  if (!pending) {
    pending = fetch(url, { cache: "force-cache" }).then(async (response) => {
      if (!response.ok) throw new Error(`静态资料载入失败（${response.status}）`);
      return await response.json() as T;
    });
    jsonCache.set(url, pending);
  }
  return pending;
}

function languageFrom(params: URLSearchParams): GameLanguage {
  return params.get("language") === "zh-TW" ? "zh-TW" : "zh-CN";
}

function otherLanguage(language: GameLanguage): GameLanguage {
  return language === "zh-CN" ? "zh-TW" : "zh-CN";
}

function searchText(value: unknown) {
  return JSON.stringify(value).toLocaleLowerCase();
}

function countBy<T>(items: T[], values: (item: T) => string[]) {
  const counts = new Map<string, number>();
  for (const item of items) {
    for (const value of values(item)) counts.set(value, (counts.get(value) || 0) + 1);
  }
  return counts;
}

async function manifest() {
  return await loadJson<StaticSnapshotManifest>("manifest.json");
}

async function entityCatalog(language: GameLanguage) {
  return await loadJson<EntityPage>(`catalog/entities.${language}.json`);
}

async function mediaCatalog(language: GameLanguage) {
  return await loadJson<MediaPage>(`catalog/media.${language}.json`);
}

async function filterEntities(params: URLSearchParams): Promise<EntityPage> {
  const language = languageFrom(params);
  const catalog = await entityCatalog(language);
  let items = [...catalog.items];
  const renderable = params.get("renderable");
  if (renderable) items = items.filter((item) => item.renderable === (renderable === "true"));
  const kindCounts = countBy(items, (item) => [item.kind]);
  const kind = params.get("kind");
  if (kind) items = items.filter((item) => item.kind === kind);
  const query = params.get("q")?.trim().toLocaleLowerCase();
  if (query) {
    const alternate = await entityCatalog(otherLanguage(language));
    const alternateById = new Map(alternate.items.map((item) => [item.id, item]));
    items = items.filter((item) => (
      searchText(item).includes(query) || searchText(alternateById.get(item.id)).includes(query)
    ));
  }
  const usageCounts = countBy(items, (item) => [item.usage]);
  const usage = params.get("usage");
  if (usage) items = items.filter((item) => item.usage === usage);
  const countryCounts = countBy(items, (item) => item.countries);
  const sideCounts = countBy(items, (item) => item.sides);
  const side = params.get("side")?.toLocaleLowerCase();
  if (side) items = items.filter((item) => item.sides.some((value) => value.toLocaleLowerCase() === side));
  const offset = Math.max(0, Number(params.get("offset") || 0));
  const limit = Math.max(1, Number(params.get("limit") || 1000));
  return {
    items: items.slice(offset, offset + limit),
    total: items.length,
    kinds: catalog.kinds.map((item) => ({ ...item, count: kindCounts.get(item.kind) || 0 })),
    usages: catalog.usages
      .map((item) => ({ ...item, count: usageCounts.get(item.usage) || 0 }))
      .filter((item) => item.count > 0),
    countries: catalog.countries
      .map((item) => ({ ...item, count: countryCounts.get(item.id) || 0 }))
      .filter((item) => item.count > 0),
    sides: [...sideCounts.entries()].sort(([left], [right]) => left.localeCompare(right))
      .filter(([id]) => Boolean(id))
      .map(([id, count]) => ({ id, count })),
    warnings: catalog.warnings,
  };
}

function mediaName(item: MediaItem) {
  return item.asset.display_name.toLocaleLowerCase();
}

async function filterMedia(params: URLSearchParams): Promise<MediaPage> {
  const language = languageFrom(params);
  const catalog = await mediaCatalog(language);
  const allItems = catalog.items;
  const kindCounts = countBy(allItems, (item) => [item.kind]);
  const groupCounts = countBy(allItems, (item) => item.groups);
  let items = [...allItems];
  const kind = params.get("kind");
  if (kind) items = items.filter((item) => item.kind === kind);
  const group = params.get("group");
  if (group) items = items.filter((item) => item.groups.includes(group));
  const query = params.get("q")?.trim().toLocaleLowerCase();
  if (query) {
    const alternate = await mediaCatalog(otherLanguage(language));
    const alternateById = new Map(alternate.items.map((item) => [item.asset.id, item]));
    items = items.filter((item) => (
      searchText(item).includes(query) || searchText(alternateById.get(item.asset.id)).includes(query)
    ));
  }
  const eventCounts = countBy(items, (item) => item.slots);
  const eventType = params.get("event_type");
  if (eventType) items = items.filter((item) => item.slots.includes(eventType));
  const sort = params.get("sort") || "name_asc";
  items.sort((left, right) => {
    if (sort === "description_asc") {
      const leftDescription = left.description || "\uffff";
      const rightDescription = right.description || "\uffff";
      return leftDescription.localeCompare(rightDescription, language, { numeric: true })
        || mediaName(left).localeCompare(mediaName(right), language, { numeric: true });
    }
    const compared = mediaName(left).localeCompare(mediaName(right), language, { numeric: true });
    return sort === "name_desc" ? -compared : compared;
  });
  const offset = Math.max(0, Number(params.get("offset") || 0));
  const limit = Math.max(1, Number(params.get("limit") || 500));
  return {
    items: items.slice(offset, offset + limit),
    total: items.length,
    kinds: ["voice", "sound", "unknown"].map((value) => ({
      kind: value as MediaPage["kinds"][number]["kind"],
      count: kindCounts.get(value) || 0,
    })),
    groups: [...groupCounts.entries()].sort(([left], [right]) => left.localeCompare(right))
      .map(([value, count]) => ({ group: value, count })),
    event_types: [...eventCounts.entries()].sort(([left], [right]) => left.localeCompare(right))
      .map(([value, count]) => ({ event_type: value, count })),
  };
}

function assetBundle(assetId: string) {
  return loadJson<StaticAssetBundle>(`assets/${encodeURIComponent(assetId)}.json`);
}

export async function staticSnapshotRequest<T>(path: string, init?: RequestInit): Promise<T> {
  if (init?.method && init.method !== "GET") throw new Error("精简网页版不支持修改本地资料");
  const url = new URL(path, window.location.origin);
  const route = url.pathname;
  const currentManifest = await manifest();
  if (route === "/api/health") {
    return {
      status: "ok",
      name: "ra2-explorer",
      version: currentManifest.app_version,
      pid: 0,
      mode: "hosted",
      edition: "pages",
    } as T;
  }
  if (route === "/api/sources") return [currentManifest.source] as T;
  if (route === "/api/stats") return currentManifest.stats as T;
  if (route === "/api/palettes" || route === "/api/player-colors" || route === "/api/resource-packs") return [] as T;
  if (route === "/api/discovery") return { candidates: [], checked_locations: [], official_sources: [] } as T;
  if (route === "/api/reference-data") return currentManifest.reference_status as T;
  if (route.includes("/api/semantic/") && route.endsWith("/diagnostics")) return currentManifest.diagnostics as T;
  if (route === "/api/entities") return await filterEntities(url.searchParams) as T;
  if (route === "/api/media") return await filterMedia(url.searchParams) as T;
  if (route === "/api/assets") return { items: [], total: 0 } satisfies AssetPage as T;
  if (route === "/api/updates/latest") {
    return {
      current_version: currentManifest.app_version,
      latest_version: currentManifest.app_version,
      update_available: false,
      release_url: "https://github.com/Hansimov/ra2-explorer/releases",
      published_at: null,
      notes: "GitHub Pages 会自动使用最新稳定网页版本。",
      provider: "github",
      asset: null,
    } satisfies UpdateInfo as T;
  }

  const entityMatch = route.match(/^\/api\/entities\/[^/]+\/([^/]+)$/);
  if (entityMatch) {
    const language = languageFrom(url.searchParams);
    return await loadJson<GameEntity>(
      `entities/${language}/${encodeURIComponent(decodeURIComponent(entityMatch[1]))}.json`,
    ) as T;
  }
  const metadataMatch = route.match(/^\/api\/assets\/([^/]+)\/metadata$/);
  if (metadataMatch) return (await assetBundle(decodeURIComponent(metadataMatch[1]))).metadata as T;
  const associationMatch = route.match(/^\/api\/assets\/([^/]+)\/associations$/);
  if (associationMatch) {
    const bundle = await assetBundle(decodeURIComponent(associationMatch[1]));
    return bundle.associations[languageFrom(url.searchParams)] as T;
  }
  const assetMatch = route.match(/^\/api\/assets\/([^/]+)$/);
  if (assetMatch) return (await assetBundle(decodeURIComponent(assetMatch[1]))).asset as T;
  throw new Error(`精简网页版未包含此资源：${route}`);
}

export function staticAudioUrl(assetId: string) {
  return snapshotUrl(`audio/${encodeURIComponent(assetId)}.ogg`);
}

export function staticEntityPreviewUrl(
  entityId: string,
  options: {
    frame?: number;
    facing?: number;
    thumbnail?: boolean;
    effectAssetId?: string;
    effectFrame?: number;
    effectShadowFrame?: number;
    effectPalette?: "unit" | "animation";
  },
) {
  const facing = options.facing ?? 0;
  if (options.effectAssetId) {
    const palette = options.effectPalette || "auto";
    const shadow = options.effectShadowFrame ?? "none";
    return snapshotUrl(
      `previews/entities/${encodeURIComponent(entityId)}/effects/${encodeURIComponent(options.effectAssetId)}/${palette}/${facing}/${options.effectFrame ?? 0}-shadow-${shadow}.webp`,
    );
  }
  const variant = options.thumbnail ? "thumbnail" : "frame";
  return snapshotUrl(
    `previews/entities/${encodeURIComponent(entityId)}/${variant}/${facing}/${options.frame ?? 0}.webp`,
  );
}

export function staticEntityModelUrl(entityId: string, frame = 0) {
  return snapshotUrl(`models/entities/${encodeURIComponent(entityId)}/${frame}.json`);
}

export function staticAssetModelUrl(assetId: string, frame = 0) {
  return snapshotUrl(`models/assets/${encodeURIComponent(assetId)}/${frame}.json`);
}

export function staticAssetPreviewUrl(
  assetId: string,
  frame: number,
  palette: "unit" | "animation" | undefined,
  shadowFrame: number | undefined,
) {
  return snapshotUrl(
    `previews/assets/${encodeURIComponent(assetId)}/${palette || "auto"}/${frame}-shadow-${shadowFrame ?? "none"}.webp`,
  );
}

export function staticPopoutUrl(params: URLSearchParams) {
  const url = new URL(window.location.href);
  url.search = params.toString();
  url.hash = "";
  return url.toString();
}
