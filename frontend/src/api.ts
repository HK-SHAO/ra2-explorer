export type SourceState = "new" | "scanning" | "ready" | "ready_with_errors" | "failed";

export interface Source {
  id: string;
  name: string;
  root_path: string;
  created_at: string;
  scanned_at: string | null;
  state: SourceState;
  error: string | null;
  archive_count: number;
  asset_count: number;
}

export interface Asset {
  id: string;
  source_id: string;
  archive_id: string | null;
  archive_path: string | null;
  ordinal: number | null;
  virtual_path: string;
  name: string | null;
  display_name: string;
  crc: number | null;
  size: number;
  format: string;
  extension: string;
  confidence: string;
  storage_kind: "mix" | "loose" | "bag";
  loose_relative_path: string | null;
}

export interface AssetPage {
  items: Asset[];
  total: number;
}

export interface FormatCount {
  format: string;
  count: number;
}

export interface Stats {
  total_assets: number;
  formats: FormatCount[];
}

export interface ShpFrame {
  index: number;
  x: number;
  y: number;
  width: number;
  height: number;
  compression: number;
}

export interface ShpMetadata {
  width: number;
  height: number;
  frame_count: number;
  frames: ShpFrame[];
}

export interface AssetMetadata {
  format: string;
  size: number;
  width?: number;
  height?: number;
  frame_count?: number;
  frames?: ShpFrame[];
  file_name?: string;
  limb_count?: number;
  voxel_count?: number;
  limbs?: Array<{ index: number; name: string; size: number[]; voxel_count: number; normals_mode: number }>;
  tile_count?: number;
  template_width?: number;
  template_height?: number;
  section_count?: number;
  section_names?: string[];
  entry_count?: number;
  label_count?: number;
  string_count?: number;
  encoding?: string;
  channels?: number;
  sample_rate?: number;
  bits_per_sample?: number;
  duration_seconds?: number;
  audio_format?: number;
  playback_transcodes_to_pcm?: boolean;
  audio_codec?: string;
  chunk_count?: number;
  color_count?: number;
  mode?: string;
  theater?: string | null;
  object_counts?: Record<string, number>;
}

export interface TextAsset {
  format: string;
  text: string;
  line_count: number;
  returned_lines: number;
  truncated: boolean;
  encoding?: string;
  section_count?: number;
  entry_count?: number;
  label_count?: number;
  string_count?: number;
}

export interface GameInstallation {
  path: string;
  name: string;
  provider: string;
  edition: string;
  markers: string[];
}

export interface DiscoveryResult {
  candidates: GameInstallation[];
  checked_locations: string[];
  official_sources: Array<{ provider: string; url: string }>;
}

export type EntityKind = "vehicle" | "infantry" | "aircraft" | "building";

export interface EntitySummary {
  id: string;
  kind: EntityKind;
  display_name: string;
  internal_name: string;
  ui_name: string | null;
  image: string;
  voxel: boolean;
  renderable: boolean;
  component_count: number;
  body_format: string | null;
  media_kinds: Array<"voice" | "sound" | "animation">;
  media_count: number;
  cost: string | null;
  strength: string | null;
  owner: string | null;
  primary: string | null;
  countries: string[];
  sides: string[];
}

export type AssetSort = "name_asc" | "name_desc" | "size_desc" | "size_asc";

export interface EntityComponentAsset {
  id: string;
  display_name: string;
  format: string;
  virtual_path: string;
  size: number;
  storage_kind: "mix" | "loose" | "bag";
}

export interface EntityComponent {
  role: string;
  expected_name: string;
  asset: EntityComponentAsset | null;
}

export type EntityDependencyKind = "weapon" | "projectile" | "warhead";

export interface EntityDependency {
  id: string;
  kind: EntityDependencyKind;
  slot: "primary" | "secondary" | "elite_primary" | "elite_secondary";
  parent: string | null;
  resolved: boolean;
  properties: Record<string, string>;
}

export interface EntityPreview {
  format: "vxl" | "shp" | null;
  frame_count: number;
  facing_count: number;
  supports_facing: boolean;
  supports_player_color: boolean;
  width?: number;
  height?: number;
  limb_count?: number;
  voxel_count?: number;
  source_frame_count?: number;
  frame_indices?: number[];
  remap_range?: number[];
  warnings?: string[];
}

export interface GameEntity extends EntitySummary {
  rules: Record<string, string>;
  art: Record<string, string>;
  components: EntityComponent[];
  dependencies: EntityDependency[];
  media: MediaAssociation[];
  preview: EntityPreview;
}

export interface MediaSample {
  name: string;
  text: string | null;
  asset: EntityComponentAsset | null;
}

export interface MediaAssociation {
  kind: "voice" | "sound" | "animation";
  slot: string;
  event: string;
  source: string;
  samples: MediaSample[];
}

export interface AssetAssociation {
  scope: "entity" | "event";
  kind: string;
  slot: string;
  event: string;
  entity: EntitySummary | null;
  text: string | null;
}

export interface AssetAssociationPage {
  items: AssetAssociation[];
  total: number;
}

export interface EntityPage {
  items: EntitySummary[];
  total: number;
  kinds: Array<{ kind: EntityKind; count: number }>;
  countries: Array<{ id: string; display_name: string; side: string; count: number }>;
  sides: Array<{ id: string; count: number }>;
  warnings: string[];
}

export type MediaKind = "voice" | "sound" | "unknown";
export type MediaSort = "name_asc" | "name_desc" | "description_asc";

export interface MediaItem {
  asset: EntityComponentAsset;
  kind: MediaKind;
  groups: string[];
  texts: string[];
  events: string[];
  slots: string[];
  entities: Array<{ id: string; display_name: string; kind: EntityKind }>;
  countries: string[];
  sides: string[];
  description: string | null;
}

export interface MediaPage {
  items: MediaItem[];
  total: number;
  kinds: Array<{ kind: MediaKind; count: number }>;
  groups: Array<{ group: string; count: number }>;
}

export interface SemanticDiagnostics {
  status: "ready" | "empty";
  entity_count: number;
  renderable_count: number;
  renderable_percent: number;
  localized_count: number;
  localized_percent: number;
  component_count: number;
  resolved_component_count: number;
  component_percent: number;
  dependency_count: number;
  unresolved_dependency_count: number;
  kinds: Array<{ kind: EntityKind; count: number; renderable_count: number }>;
  missing_components: Array<{ role: string; count: number }>;
  warnings: string[];
}

export interface PlayerColor {
  id: string;
  rgb: number[];
  hex: string;
}

export interface EntityPreviewOptions {
  frame?: number;
  facing?: number;
  playerColor?: string;
  paletteId?: string;
  scale?: number;
}

export interface ReferenceStatus {
  available: boolean;
  manifest_valid?: boolean;
  repository?: string;
  revision?: string;
  downloaded_at?: string;
  name_count?: number;
  builtin_name_count?: number;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    let message = `请求失败（${response.status}）`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      // Keep the status-based fallback when the response is not JSON.
    }
    throw new Error(message);
  }
  return (await response.json()) as T;
}

export const api = {
  sources: () => request<Source[]>("/api/sources"),
  discovery: () => request<DiscoveryResult>("/api/discovery"),
  addSource: (path: string, name?: string) =>
    request<Source>("/api/sources", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path, name: name || null }),
    }),
  scanSource: (id: string) => request<Source>(`/api/sources/${id}/scan`, { method: "POST" }),
  assets: (
    sourceId: string,
    query: string,
    formats: string[],
    offset = 0,
    limit = 500,
    sort: AssetSort = "name_asc",
  ) => {
    const params = new URLSearchParams({
      source_id: sourceId,
      limit: String(limit),
      offset: String(offset),
      sort,
    });
    if (query.trim()) params.set("q", query.trim());
    if (formats.length) params.set("formats", formats.join(","));
    return request<AssetPage>(`/api/assets?${params}`);
  },
  entities: (
    sourceId: string,
    query: string,
    kind: EntityKind | "",
    renderable: "" | "true" | "false" = "",
  ) => {
    const params = new URLSearchParams({ source_id: sourceId, limit: "1000" });
    if (query.trim()) params.set("q", query.trim());
    if (kind) params.set("kind", kind);
    if (renderable) params.set("renderable", renderable);
    return request<EntityPage>(`/api/entities?${params}`);
  },
  media: (
    sourceId: string,
    query: string,
    kind: MediaKind,
    group = "",
    offset = 0,
    limit = 500,
    sort: MediaSort = "name_asc",
  ) => {
    const params = new URLSearchParams({
      source_id: sourceId,
      kind,
      limit: String(limit),
      offset: String(offset),
      sort,
    });
    if (query.trim()) params.set("q", query.trim());
    if (group) params.set("group", group);
    return request<MediaPage>(`/api/media?${params}`);
  },
  entity: (sourceId: string, entityId: string) =>
    request<GameEntity>(
      `/api/entities/${encodeURIComponent(sourceId)}/${encodeURIComponent(entityId)}`,
    ).then((entity) => ({
      ...entity,
      body_format: entity.body_format ?? entity.components?.find((item) => item.role === "body")?.asset?.format ?? null,
      media_kinds: entity.media_kinds ?? [],
      media_count: entity.media_count ?? entity.media?.length ?? 0,
      components: entity.components ?? [],
      dependencies: entity.dependencies ?? [],
      media: entity.media ?? [],
      countries: entity.countries ?? [],
      sides: entity.sides ?? [],
      rules: entity.rules ?? {},
      art: entity.art ?? {},
      preview: entity.preview ?? {
        format: null,
        frame_count: 1,
        facing_count: 1,
        supports_facing: false,
        supports_player_color: false,
      },
    })),
  asset: (id: string) => request<Asset>(`/api/assets/${id}`),
  assetAssociations: (id: string) =>
    request<AssetAssociationPage>(`/api/assets/${id}/associations`),
  stats: (sourceId: string) => request<Stats>(`/api/stats?source_id=${encodeURIComponent(sourceId)}`),
  palettes: (sourceId: string) =>
    request<Asset[]>(`/api/palettes?source_id=${encodeURIComponent(sourceId)}`),
  semanticDiagnostics: (sourceId: string) =>
    request<SemanticDiagnostics>(
      `/api/semantic/${encodeURIComponent(sourceId)}/diagnostics?limit=8`,
    ),
  playerColors: () => request<PlayerColor[]>("/api/player-colors"),
  shp: (assetId: string) => request<ShpMetadata>(`/api/assets/${assetId}/shp`),
  metadata: (assetId: string) => request<AssetMetadata>(`/api/assets/${assetId}/metadata`),
  text: (assetId: string, query = "") => {
    const params = new URLSearchParams({ limit: "400" });
    if (query.trim()) params.set("q", query.trim());
    return request<TextAsset>(`/api/assets/${assetId}/text?${params}`);
  },
  referenceStatus: () => request<ReferenceStatus>("/api/reference-data"),
  syncNames: () =>
    request<ReferenceStatus>("/api/reference-data/names/sync", { method: "POST" }),
  contentUrl: (assetId: string) => `/api/assets/${assetId}/content`,
  mediaUrl: (assetId: string) => `/api/assets/${assetId}/media`,
  videoUrl: (assetId: string) => `/api/assets/${assetId}/video.mp4`,
  entityPreviewUrl: (
    sourceId: string,
    entityId: string,
    options: EntityPreviewOptions = {},
  ) => {
    const params = new URLSearchParams({
      frame: String(options.frame ?? 0),
      facing: String(options.facing ?? 0),
      scale: String(options.scale ?? 4),
    });
    if (options.playerColor) params.set("player_color", options.playerColor);
    if (options.paletteId) params.set("palette_id", options.paletteId);
    return `/api/entities/${encodeURIComponent(sourceId)}/${encodeURIComponent(entityId)}/preview.png?${params}`;
  },
  entityModelUrl: (
    sourceId: string,
    entityId: string,
    options: EntityPreviewOptions = {},
  ) => {
    const params = new URLSearchParams({ frame: String(options.frame ?? 0) });
    if (options.playerColor) params.set("player_color", options.playerColor);
    if (options.paletteId) params.set("palette_id", options.paletteId);
    return `/api/entities/${encodeURIComponent(sourceId)}/${encodeURIComponent(entityId)}/model.json?${params}`;
  },
  assetModelUrl: (assetId: string, frame = 0, playerColor = "", paletteId = "") => {
    const params = new URLSearchParams({ frame: String(frame) });
    if (playerColor) params.set("player_color", playerColor);
    if (paletteId) params.set("palette_id", paletteId);
    return `/api/assets/${assetId}/model.json?${params}`;
  },
  previewUrl: (
    assetId: string,
    frame: number,
    paletteId: string,
    scale = 4,
    playerColor = "",
  ) => {
    const params = new URLSearchParams({ frame: String(frame), scale: String(scale) });
    if (paletteId) params.set("palette_id", paletteId);
    if (playerColor) params.set("player_color", playerColor);
    return `/api/assets/${assetId}/preview.png?${params}`;
  },
};
