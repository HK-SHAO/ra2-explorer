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
  storage_kind: "mix" | "loose";
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
  color_count?: number;
  mode?: string;
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
  createDemo: () => request<Source>("/api/demo", { method: "POST" }),
  scanSource: (id: string) => request<Source>(`/api/sources/${id}/scan`, { method: "POST" }),
  assets: (sourceId: string, query: string, format: string) => {
    const params = new URLSearchParams({ source_id: sourceId, limit: "500" });
    if (query.trim()) params.set("q", query.trim());
    if (format) params.set("format", format);
    return request<AssetPage>(`/api/assets?${params}`);
  },
  asset: (id: string) => request<Asset>(`/api/assets/${id}`),
  stats: (sourceId: string) => request<Stats>(`/api/stats?source_id=${encodeURIComponent(sourceId)}`),
  palettes: (sourceId: string) =>
    request<Asset[]>(`/api/palettes?source_id=${encodeURIComponent(sourceId)}`),
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
  previewUrl: (assetId: string, frame: number, paletteId: string, scale = 4) => {
    const params = new URLSearchParams({ frame: String(frame), scale: String(scale) });
    if (paletteId) params.set("palette_id", paletteId);
    return `/api/assets/${assetId}/preview.png?${params}`;
  },
};
