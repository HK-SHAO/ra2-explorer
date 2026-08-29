import { FormEvent, lazy, ReactNode, Suspense, useEffect, useMemo, useState } from "react";

import {
  api,
  Asset,
  AssetAssociationPage,
  AssetMetadata,
  AssetSort,
  DiscoveryResult,
  EntityDependency,
  EntityKind,
  EntitySummary,
  GameEntity,
  GameInstallation,
  MediaItem,
  MediaKind,
  PlayerColor,
  Source,
  Stats,
  TextAsset,
} from "./api";

const VoxelViewer = lazy(async () => ({ default: (await import("./VoxelViewer")).VoxelViewer }));

function VoxelPreview({ url, label }: { url: string; label: string }) {
  return <Suspense fallback={<div className="voxel-viewer"><div className="voxel-status">正在载入三维视图…</div></div>}><VoxelViewer url={url} label={label} /></Suspense>;
}

type IconName =
  | "archive"
  | "chevron"
  | "close"
  | "download"
  | "file"
  | "folder"
  | "grid"
  | "image"
  | "info"
  | "list"
  | "pause"
  | "play"
  | "popout"
  | "refresh"
  | "search"
  | "settings"
  | "spark"
  | "swatch"
  | "unit";

function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, ReactNode> = {
    archive: <><path d="M4 7.5h16v12H4z" /><path d="M3 4.5h18v3H3zM9 11h6" /></>,
    chevron: <path d="m9 18 6-6-6-6" />,
    close: <><path d="m6 6 12 12M18 6 6 18" /></>,
    download: <><path d="M12 3v12m0 0 4-4m-4 4-4-4" /><path d="M5 20h14" /></>,
    file: <><path d="M6 3h8l4 4v14H6z" /><path d="M14 3v5h5" /></>,
    folder: <path d="M3 6h7l2 2h9v11H3z" />,
    grid: <><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></>,
    image: <><rect x="3" y="4" width="18" height="16" rx="2" /><circle cx="9" cy="10" r="2" /><path d="m4 17 5-4 4 3 3-2 4 3" /></>,
    info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v6m0-10h.01" /></>,
    list: <><path d="M8 6h13M8 12h13M8 18h13" /><path d="M3 6h.01M3 12h.01M3 18h.01" /></>,
    pause: <><path d="M9 7v10M15 7v10" /></>,
    play: <path d="m9 7 8 5-8 5z" />,
    popout: <><path d="M13 4h7v7M20 4l-9 9" /><path d="M18 13v7H4V6h7" /></>,
    refresh: <><path d="M20 11a8 8 0 0 0-14.8-4L3 10" /><path d="M3 5v5h5M4 13a8 8 0 0 0 14.8 4L21 14" /><path d="M21 19v-5h-5" /></>,
    search: <><circle cx="11" cy="11" r="7" /><path d="m16 16 5 5" /></>,
    settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.03 1.56V21h-4v-.08A1.7 1.7 0 0 0 9 19.37a1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.63 15a1.7 1.7 0 0 0-1.55-1.03H3v-4h.08A1.7 1.7 0 0 0 4.63 9a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.83-2.83.06.06A1.7 1.7 0 0 0 9 4.63a1.7 1.7 0 0 0 1-1.55V3h4v.08A1.7 1.7 0 0 0 15 4.63a1.7 1.7 0 0 0 1.88-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0 0 19.37 9a1.7 1.7 0 0 0 1.55 1.03H21v4h-.08A1.7 1.7 0 0 0 19.4 15Z" /></>,
    spark: <><path d="m12 3 1.1 4.2L17 9l-3.9 1.8L12 15l-1.1-4.2L7 9l3.9-1.8z" /><path d="m19 15 .6 2.4L22 18.5l-2.4 1.1L19 22l-.6-2.4-2.4-1.1 2.4-1.1z" /></>,
    swatch: <><path d="M4 4h6v16H4zM10 7h5v13h-5zM15 10h5v10h-5z" /><path d="M7 16h.01M12.5 16h.01M17.5 16h.01" /></>,
    unit: <><path d="M5 10h11l3 3v4H5z" /><path d="M8 10V7h6l2 3M14 7l3-2M4 17h16" /><circle cx="8" cy="18" r="2" /><circle cx="17" cy="18" r="2" /></>,
  };
  return (
    <svg className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <g stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</g>
    </svg>
  );
}

const formatLabels: Record<string, string> = {
  shp: "SHP 动画",
  pal: "PAL 配色表",
  mix: "MIX 归档",
  ini: "INI 配置",
  csf: "CSF 文本",
  vxl: "VXL 模型",
  hva: "HVA 动画",
  tmp: "TMP 地块",
  pcx: "PCX 图像",
  map: "地图配置",
  text: "文本",
  wav: "WAV 音频",
  bag_audio: "BAG 音频",
  aud: "AUD 音频",
  bag: "音频包",
  idx: "音频索引",
  vpl: "VPL 光照",
  fnt: "游戏字体",
  video: "过场视频",
  binary: "二进制",
  unknown: "其他",
};

const entityKindLabels: Record<EntityKind, string> = {
  vehicle: "载具",
  infantry: "步兵",
  aircraft: "航空器",
  building: "建筑",
};

const componentRoleLabels: Record<string, string> = {
  body: "主体",
  body_hva: "主体动画",
  turret: "炮塔",
  turret_hva: "炮塔动画",
  barrel: "炮管",
  barrel_hva: "炮管动画",
  cameo: "建造图标",
  alt_cameo: "升级图标",
};

const ruleLabels: Record<string, string> = {
  cost: "造价",
  strength: "生命值",
  armor: "装甲",
  speed: "速度",
  sight: "视野",
  tech_level: "科技等级",
  category: "分类",
  owner: "阵营",
  prerequisite: "前置建筑",
  primary: "主武器",
  secondary: "副武器",
  elite_primary: "精英主武器",
  elite_secondary: "精英副武器",
  movement_zone: "移动区域",
};

const dependencyKindLabels: Record<EntityDependency["kind"], string> = {
  weapon: "武器",
  projectile: "弹体",
  warhead: "弹头",
};

const dependencySlotLabels: Record<EntityDependency["slot"], string> = {
  primary: "主武器",
  secondary: "副武器",
  elite_primary: "精英主武器",
  elite_secondary: "精英副武器",
};

const dependencyPropertyLabels: Record<string, string> = {
  damage: "伤害",
  rate_of_fire: "射速",
  range: "射程",
  minimum_range: "最近射程",
  burst: "连发",
  speed: "速度",
  projectile: "弹体",
  warhead: "弹头",
  report: "音效",
  animation: "动画",
  image: "图像",
  arcing: "抛物线",
  invisible: "不可见",
  proximity: "近炸",
  rotation: "转向",
  acceleration: "加速度",
  inaccurate: "散布",
  verses: "装甲倍率",
  cell_spread: "范围",
  percent_at_max: "边缘伤害",
  infantry_death: "步兵死亡",
  animation_list: "命中动画",
  wall: "墙体",
  wood: "木质",
  radiation: "辐射",
};

const mediaSlotLabels: Record<string, string> = {
  select: "选中",
  move: "移动",
  attack: "攻击",
  feedback: "受击",
  special_attack: "特殊攻击",
  capture: "占领",
  harvest: "采集",
  die: "阵亡",
  create: "建造完成",
  deploy: "部署",
  undeploy: "取消部署",
  enter: "进入目标",
  enter_transport: "进入载具",
  leave_transport: "离开载具",
  movement: "行驶",
  start_moving: "开始移动",
  stop_moving: "停止移动",
  turret_rotate: "炮塔转动",
  activate: "启动",
  deactivate: "关闭",
  cloak: "隐形",
  uncloak: "解除隐形",
  chrono_in: "超时空进入",
  chrono_out: "超时空离开",
  crashing: "坠毁",
  impact_land: "撞击地面",
  sinking: "沉没",
  impact_water: "落水",
  primary: "主武器",
  secondary: "副武器",
  elite_primary: "精英主武器",
  elite_secondary: "精英副武器",
  body_animation: "主体动画",
  body_hva: "主体动作",
  turret_hva: "炮塔动作",
  barrel_hva: "炮管动作",
};

const mediaGroupLabels: Record<string, string> = {
  unit_voice: "单位语音",
  eva_voice: "EVA 播报",
  mission_voice: "任务对白",
  other_voice: "其他语音",
  combat_sound: "战斗音效",
  unit_sound: "单位动作",
  ambient_sound: "环境音效",
  other_sound: "其他音效",
  unclassified: "未关联音频",
};

const sideLabels: Record<string, string> = {
  GDI: "盟军",
  Nod: "苏军",
  ThirdSide: "尤里",
  Civilian: "平民",
  Mutant: "特殊",
};

const mapObjectLabels: Record<string, string> = {
  structure: "建筑",
  unit: "载具",
  infantry: "步兵",
  aircraft: "航空器",
  terrain: "地形对象",
  waypoint: "路径点",
};

const playerColorLabels: Record<string, string> = {
  red: "红色",
  blue: "蓝色",
  green: "绿色",
  yellow: "黄色",
  orange: "橙色",
  purple: "紫色",
  cyan: "青色",
  gray: "灰色",
};

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(value < 10 * 1024 ? 1 : 0)} KB`;
  return `${(value / 1024 ** 2).toFixed(1)} MB`;
}

function formatDuration(value: number) {
  const total = Math.max(0, Math.round(value));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

function crcLabel(value: number | null) {
  return value === null ? "—" : value.toString(16).toUpperCase().padStart(8, "0");
}

function stateLabel(state: Source["state"]) {
  return {
    new: "等待扫描",
    scanning: "扫描中",
    ready: "索引就绪",
    ready_with_errors: "部分就绪",
    failed: "扫描失败",
  }[state];
}

function assetIcon(format: string): IconName {
  if (["vxl", "hva"].includes(format)) return "unit";
  if (["shp", "tmp", "pcx"].includes(format)) return "image";
  if (format === "map") return "grid";
  if (format === "video") return "play";
  if (format === "pal") return "swatch";
  if (format === "mix") return "archive";
  if (["wav", "aud", "bag_audio"].includes(format)) return "play";
  return "file";
}

type LayoutMode = "list" | "grid";
type EntitySort = "name_asc" | "name_desc" | "cost_desc" | "strength_desc";

const audioFormats = ["bag_audio", "wav", "aud"];
const imageFormats = ["shp", "tmp", "pcx", "pal", "map"];
const defaultVisibleFormats = [
  "vxl", "hva", "shp", "video", "bag_audio", "wav", "aud",
];
const assetCategories: Array<{
  id: string;
  label: string;
  formats: string[];
  icon: IconName;
}> = [
  { id: "voices", label: "游戏语音", formats: ["bag_audio", "wav", "aud"], icon: "play" },
  { id: "sounds", label: "游戏音效", formats: ["bag_audio", "wav", "aud"], icon: "play" },
  { id: "animations", label: "动画", formats: ["shp", "hva", "video"], icon: "image" },
  { id: "maps", label: "地图", formats: ["map"], icon: "grid" },
  { id: "images", label: "图像", formats: ["pcx"], icon: "image" },
  { id: "terrain", label: "地形素材", formats: ["tmp"], icon: "image" },
  { id: "rules", label: "规则文本", formats: ["ini", "csf", "text"], icon: "file" },
];

const entityKindOrder: EntityKind[] = ["vehicle", "aircraft", "infantry", "building"];

const entityTagLabels: Record<string, string> = {
  "body:vxl": "三维体素",
  "body:shp": "帧动画",
  "media:voice": "带语音",
  "media:sound": "带音效",
  "media:animation": "带动画",
};

function entityTagMatches(entity: EntitySummary, tag: string) {
  if (!tag) return true;
  const [group, value] = tag.split(":", 2);
  if (group === "body") return entity.body_format === value;
  if (group === "media") return (entity.media_kinds ?? []).includes(value as "voice" | "sound" | "animation");
  return true;
}

function sortEntities(entities: EntitySummary[], sort: EntitySort) {
  const selected = [...entities];
  const numeric = (value: string | null) => Number.parseInt(value || "0", 10) || 0;
  selected.sort((left, right) => {
    if (sort === "cost_desc") return numeric(right.cost) - numeric(left.cost) || left.display_name.localeCompare(right.display_name, "zh-CN");
    if (sort === "strength_desc") return numeric(right.strength) - numeric(left.strength) || left.display_name.localeCompare(right.display_name, "zh-CN");
    const compared = left.display_name.localeCompare(right.display_name, "zh-CN", { numeric: true });
    return sort === "name_desc" ? -compared : compared;
  });
  return selected;
}

function initialVisibleFormats() {
  try {
    const stored = JSON.parse(window.localStorage.getItem("ra2exp-visible-formats-v2") || "null");
    if (Array.isArray(stored) && stored.every((item) => typeof item === "string")) return stored as string[];
  } catch {
    // Ignore invalid local preferences and use the product defaults.
  }
  return defaultVisibleFormats;
}

function categoryCount(stats: Stats, formats: string[]) {
  const selected = new Set(formats);
  return stats.formats.reduce(
    (total, item) => total + (selected.has(item.format) ? item.count : 0),
    0,
  );
}

function ExplorerApp() {
  const [view, setView] = useState<"assets" | "entities">("entities");
  const [sources, setSources] = useState<Source[]>([]);
  const [sourceId, setSourceId] = useState("");
  const [assets, setAssets] = useState<Asset[]>([]);
  const [assetPageLoading, setAssetPageLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState<Stats>({ total_assets: 0, formats: [] });
  const [palettes, setPalettes] = useState<Asset[]>([]);
  const [playerColors, setPlayerColors] = useState<PlayerColor[]>([]);
  const [assetQuery, setAssetQuery] = useState("");
  const [assetCategory, setAssetCategory] = useState("animations");
  const [assetFormatTag, setAssetFormatTag] = useState("");
  const [assetSort, setAssetSort] = useState<AssetSort>("name_asc");
  const [enabledFormats, setEnabledFormats] = useState<string[]>(initialVisibleFormats);
  const [layout, setLayout] = useState<LayoutMode>(() =>
    window.localStorage.getItem("ra2exp-layout") === "grid" ? "grid" : "list",
  );
  const [entities, setEntities] = useState<EntitySummary[]>([]);
  const [entityKinds, setEntityKinds] = useState<Array<{ kind: EntityKind; count: number }>>([]);
  const [entityCountries, setEntityCountries] = useState<Array<{ id: string; display_name: string; side: string; count: number }>>([]);
  const [entitySides, setEntitySides] = useState<Array<{ id: string; count: number }>>([]);
  const [entityKind, setEntityKind] = useState<EntityKind | "">("vehicle");
  const [entityQuery, setEntityQuery] = useState("");
  const [entityTag, setEntityTag] = useState("");
  const [entityCountry, setEntityCountry] = useState("");
  const [entitySide, setEntitySide] = useState("");
  const [entitySort, setEntitySort] = useState<EntitySort>("name_asc");
  const [selectedEntityId, setSelectedEntityId] = useState("");
  const [selectedEntity, setSelectedEntity] = useState<GameEntity | null>(null);
  const [entityLoading, setEntityLoading] = useState(false);
  const [entityDetailLoading, setEntityDetailLoading] = useState(false);
  const [mediaItems, setMediaItems] = useState<MediaItem[]>([]);
  const [mediaTotal, setMediaTotal] = useState(0);
  const [mediaGroups, setMediaGroups] = useState<Array<{ group: string; count: number }>>([]);
  const [mediaKindCounts, setMediaKindCounts] = useState<Array<{ kind: MediaKind; count: number }>>([]);
  const [mediaGroup, setMediaGroup] = useState("");
  const [mediaLoading, setMediaLoading] = useState(false);
  const [playingMediaId, setPlayingMediaId] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [selected, setSelected] = useState<Asset | null>(null);
  const [metadata, setMetadata] = useState<AssetMetadata | null>(null);
  const [associations, setAssociations] = useState<AssetAssociationPage | null>(null);
  const [textAsset, setTextAsset] = useState<TextAsset | null>(null);
  const [textQuery, setTextQuery] = useState("");
  const [frame, setFrame] = useState(0);
  const [paletteId, setPaletteId] = useState("");
  const [playing, setPlaying] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [discovery, setDiscovery] = useState<DiscoveryResult>({ candidates: [], checked_locations: [], official_sources: [] });
  const [discoveryLoaded, setDiscoveryLoaded] = useState(false);

  const activeSource = sources.find((item) => item.id === sourceId) ?? null;
  const sourceRevision = activeSource?.scanned_at || "";
  const visibleCategories = assetCategories.filter((item) =>
    item.formats.some((formatName) => enabledFormats.includes(formatName)),
  );
  const selectedCategory = visibleCategories.find((item) => item.id === assetCategory)
    || visibleCategories[0]
    || null;
  const selectedCategoryId = selectedCategory?.id || "";
  const isMediaCategory = selectedCategoryId === "voices" || selectedCategoryId === "sounds";
  const mediaKind: MediaKind = selectedCategoryId === "voices" ? "voice" : "sound";
  const categoryFormats = (selectedCategory?.formats || [])
    .filter((formatName) => enabledFormats.includes(formatName));
  const assetFormats = assetFormatTag && categoryFormats.includes(assetFormatTag)
    ? [assetFormatTag]
    : categoryFormats;
  const assetFormatKey = assetFormats.join(",");
  const kindEntities = useMemo(
    () => entities.filter((entity) => !entityKind || entity.kind === entityKind),
    [entities, entityKind],
  );
  const scopedEntities = useMemo(
    () => kindEntities.filter((entity) =>
      (!entitySide || entity.sides.includes(entitySide))
      && (!entityCountry || entity.countries.includes(entityCountry))),
    [kindEntities, entitySide, entityCountry],
  );
  const visibleEntities = useMemo(
    () => sortEntities(scopedEntities.filter((entity) => entityTagMatches(entity, entityTag)), entitySort),
    [scopedEntities, entityTag, entitySort],
  );
  const entityTags = Object.keys(entityTagLabels)
    .map((tag) => ({ tag, count: scopedEntities.filter((entity) => entityTagMatches(entity, tag)).length }))
    .filter((item) => item.count > 0);

  function updateLayout(next: LayoutMode) {
    setLayout(next);
    window.localStorage.setItem("ra2exp-layout", next);
  }

  function updateEnabledFormats(next: string[]) {
    const unique = [...new Set(next)];
    setEnabledFormats(unique);
    window.localStorage.setItem("ra2exp-visible-formats-v2", JSON.stringify(unique));
  }

  function selectEntityKind(kind: EntityKind) {
    setView("entities");
    setEntityKind(kind);
  }

  function selectAssetCategory(category: string) {
    setView("assets");
    setAssetCategory(category);
    setAssetFormatTag("");
    setMediaGroup("");
  }

  function openAddSource() {
    setAddOpen(true);
    if (discoveryLoaded) return;
    setDiscoveryLoaded(true);
    api.discovery()
      .then(setDiscovery)
      .catch(() => setDiscovery({ candidates: [], checked_locations: [], official_sources: [] }));
  }

  useEffect(() => {
    if (selectedCategoryId && selectedCategoryId !== assetCategory) {
      setAssetCategory(selectedCategoryId);
    }
  }, [assetCategory, selectedCategoryId]);

  useEffect(() => {
    if (assetFormatTag && !categoryFormats.includes(assetFormatTag)) setAssetFormatTag("");
  }, [assetFormatTag, categoryFormats]);

  useEffect(() => {
    if (view !== "entities" || entityLoading) return;
    if (!visibleEntities.some((entity) => entity.id === selectedEntityId)) {
      setSelectedEntityId(visibleEntities[0]?.id || "");
    }
  }, [view, entityLoading, visibleEntities, selectedEntityId]);

  async function refreshSources(preferredId?: string) {
    const next = await api.sources();
    setSources(next);
    const candidate = preferredId || sourceId;
    setSourceId(next.some((item) => item.id === candidate) ? candidate : next[0]?.id || "");
  }

  useEffect(() => {
    Promise.all([
      api.sources(),
      api.playerColors().catch(() => []),
    ])
      .then(([nextSources, nextPlayerColors]) => {
        setSources(nextSources);
        setSourceId(nextSources[0]?.id || "");
        setPlayerColors(nextPlayerColors);
      })
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    setSelectedId("");
    setSelected(null);
    setSelectedEntityId("");
    setSelectedEntity(null);
    setAssociations(null);
    setAssets([]);
    setEntities([]);
    setMediaItems([]);
    setTotal(0);
    setMediaTotal(0);
    if (!sourceId) {
      setStats({ total_assets: 0, formats: [] });
      setPalettes([]);
      return;
    }
    let cancelled = false;
    Promise.all([api.stats(sourceId), api.palettes(sourceId)])
      .then(([nextStats, nextPalettes]) => {
        if (cancelled) return;
        setStats(nextStats);
        setPalettes(nextPalettes);
      })
      .catch((reason: Error) => !cancelled && setError(reason.message));
    return () => { cancelled = true; };
  }, [sourceId, sourceRevision]);

  useEffect(() => {
    if (!sourceId || view !== "assets" || isMediaCategory) return;
    if (!assetFormats.length) {
      setAssets([]);
      setTotal(0);
      setSelectedId("");
      setAssetPageLoading(false);
      return;
    }
    let cancelled = false;
    setAssetPageLoading(true);
    setAssets([]);
    setTotal(0);
    const timer = window.setTimeout(() => {
      api.assets(sourceId, assetQuery, assetFormatKey ? assetFormatKey.split(",") : [], 0, 500, assetSort)
        .then((page) => {
          if (cancelled) return;
          setAssets(page.items);
          setTotal(page.total);
          setSelectedId((current) =>
            page.items.some((asset) => asset.id === current)
              ? current
              : page.items.find((asset) => asset.format === "vxl")?.id
                || page.items.find((asset) => asset.format === "bag_audio")?.id
                || page.items.find((asset) => asset.format === "shp")?.id
                || page.items[0]?.id
                || "",
          );
        })
        .catch((reason: Error) => !cancelled && setError(reason.message))
        .finally(() => !cancelled && setAssetPageLoading(false));
    }, assetQuery ? 180 : 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [sourceId, sourceRevision, assetQuery, assetFormatKey, assetSort, view, isMediaCategory]);

  useEffect(() => {
    if (!sourceId || view !== "assets" || !isMediaCategory) return;
    let cancelled = false;
    setMediaLoading(true);
    setMediaItems([]);
    setMediaTotal(0);
    setPlayingMediaId("");
    const timer = window.setTimeout(() => {
      api.media(sourceId, assetQuery, mediaKind, mediaGroup)
        .then((page) => {
          if (cancelled) return;
          setMediaItems(page.items);
          setMediaTotal(page.total);
          setMediaGroups(page.groups);
          setMediaKindCounts(page.kinds);
          setSelectedId((current) => page.items.some((item) => item.asset.id === current)
            ? current
            : page.items[0]?.asset.id || "");
        })
        .catch((reason: Error) => !cancelled && setError(reason.message))
        .finally(() => !cancelled && setMediaLoading(false));
    }, assetQuery ? 180 : 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [sourceId, sourceRevision, assetQuery, mediaKind, mediaGroup, view, isMediaCategory]);

  useEffect(() => {
    if (!sourceId || view !== "entities") return;
    let cancelled = false;
    setEntityLoading(true);
    setEntities([]);
    setSelectedEntityId("");
    setSelectedEntity(null);
    const timer = window.setTimeout(() => {
      api.entities(sourceId, entityQuery, "", "true")
        .then((page) => {
          if (cancelled) return;
          setEntities(page.items);
          setEntityKinds(page.kinds);
          setEntityCountries(page.countries);
          setEntitySides(page.sides);
          setSelectedEntityId((current) =>
            page.items.some((entity) => entity.id === current)
              ? current
              : page.items.find((entity) => entity.renderable)?.id || page.items[0]?.id || "",
          );
        })
        .catch((reason: Error) => !cancelled && setError(reason.message))
        .finally(() => !cancelled && setEntityLoading(false));
    }, entityQuery ? 180 : 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [sourceId, sourceRevision, entityQuery, view]);

  useEffect(() => {
    if (!sourceId || !selectedEntityId || view !== "entities") {
      setSelectedEntity(null);
      setEntityDetailLoading(false);
      return;
    }
    let cancelled = false;
    setSelectedEntity(null);
    setEntityDetailLoading(true);
    api.entity(sourceId, selectedEntityId)
      .then((entity) => !cancelled && setSelectedEntity(entity))
      .catch((reason: Error) => !cancelled && setError(reason.message))
      .finally(() => !cancelled && setEntityDetailLoading(false));
    return () => { cancelled = true; };
  }, [sourceId, sourceRevision, selectedEntityId, view]);

  useEffect(() => {
    setFrame(0);
    setPlaying(false);
    setMetadata(null);
    setTextAsset(null);
    setTextQuery("");
    setPaletteId("");
    if (!selectedId) {
      setSelected(null);
      return;
    }
    let cancelled = false;
    Promise.all([api.asset(selectedId), api.metadata(selectedId)])
      .then(([asset, nextMetadata]) => {
        if (cancelled) return;
        setSelected(asset);
        setMetadata(nextMetadata);
      })
      .catch((reason: Error) => !cancelled && setError(reason.message));
    return () => { cancelled = true; };
  }, [selectedId]);

  useEffect(() => {
    setAssociations(null);
    if (!selected || ![...audioFormats, "shp", "hva", "vxl", "video"].includes(selected.format)) {
      return;
    }
    let cancelled = false;
    api.assetAssociations(selected.id)
      .then((result) => !cancelled && setAssociations(result))
      .catch(() => undefined);
    return () => { cancelled = true; };
  }, [selected]);

  useEffect(() => {
    if (!playing || !selected || !["shp", "hva"].includes(selected.format) || !metadata?.frame_count || metadata.frame_count < 2) return;
    const timer = window.setInterval(
      () => setFrame((current) => (current + 1) % metadata.frame_count!),
      selected.format === "hva" ? 350 : 140,
    );
    return () => window.clearInterval(timer);
  }, [playing, metadata, selected]);

  useEffect(() => {
    if (!selected || !["ini", "map", "text", "csf"].includes(selected.format)) {
      setTextAsset(null);
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      api.text(selected.id, textQuery)
        .then((result) => !cancelled && setTextAsset(result))
        .catch((reason: Error) => !cancelled && setError(reason.message));
    }, textQuery ? 180 : 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [selected, textQuery]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(""), 3200);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const previewUrl = useMemo(() => {
    if (!selected || !imageFormats.includes(selected.format)) return "";
    const scale = selected.format === "pcx" ? 1 : selected.format === "pal" ? 3 : selected.format === "shp" ? 5 : 4;
    return api.previewUrl(selected.id, frame, paletteId, scale);
  }, [selected, frame, paletteId]);

  async function runAction(action: () => Promise<Source>, message: string) {
    setBusy(true);
    setError("");
    try {
      const source = await action();
      await refreshSources(source.id);
      setNotice(message);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "操作失败");
    } finally {
      setBusy(false);
    }
  }

  async function loadMoreAssets() {
    if (assetPageLoading || assets.length >= total || !sourceId || !assetFormats.length) return;
    setAssetPageLoading(true);
    try {
      const page = await api.assets(sourceId, assetQuery, assetFormats, assets.length, 500, assetSort);
      setAssets((current) => {
        const known = new Set(current.map((asset) => asset.id));
        return [...current, ...page.items.filter((asset) => !known.has(asset.id))];
      });
      setTotal(page.total);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "载入失败");
    } finally {
      setAssetPageLoading(false);
    }
  }

  async function loadMoreMedia() {
    if (mediaLoading || mediaItems.length >= mediaTotal || !sourceId) return;
    setMediaLoading(true);
    try {
      const page = await api.media(sourceId, assetQuery, mediaKind, mediaGroup, mediaItems.length);
      setMediaItems((current) => {
        const known = new Set(current.map((item) => item.asset.id));
        return [...current, ...page.items.filter((item) => !known.has(item.asset.id))];
      });
      setMediaTotal(page.total);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "载入失败");
    } finally {
      setMediaLoading(false);
    }
  }

  if (loading) {
    return <div className="boot"><div className="radar"><span /></div><p>正在接入本地资料库…</p></div>;
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true"><span>R</span><i /></div>
          <div><strong>RA2 Explorer</strong></div>
        </div>
        <div className="topbar-actions">
          {activeSource && <span className={`source-status ${activeSource.state}`}><i />{stateLabel(activeSource.state)}</span>}
          <button className="button ghost compact" onClick={openAddSource}><Icon name="folder" />添加目录</button>
          <button className="button ghost compact settings-button" onClick={() => setSettingsOpen(true)}><Icon name="settings" />显示设置</button>
          <button className="button primary compact" disabled={busy || !activeSource} onClick={() => activeSource && runAction(() => api.scanSource(activeSource.id), "目录索引已更新")}><Icon name="refresh" />重新扫描</button>
        </div>
      </header>

      {sources.length === 0 ? (
        <EmptyLibrary
          busy={busy}
          discoveries={discovery.candidates}
          onAdd={openAddSource}
          onImport={(installation) => runAction(
            () => api.addSource(installation.path, installation.name),
            `${installation.edition} 已导入`,
          )}
        />
      ) : (
        <main className="workspace">
          <aside className="source-panel panel">
            {sources.length > 1 && <section className="source-heading">
              <label className="source-select-wrap">
                <select value={sourceId} onChange={(event) => setSourceId(event.target.value)} aria-label="选择资料库">
                  {sources.map((source) => <option key={source.id} value={source.id}>{source.name}</option>)}
                </select>
                <Icon name="chevron" size={15} />
              </label>
            </section>}

            <nav className="library-tree" aria-label="浏览分类" tabIndex={0}>
              <section className="tree-branch">
                <div className="tree-parent"><Icon name="unit" /><strong>单位</strong><em>{entityKinds.reduce((count, item) => count + item.count, 0)}</em></div>
                <div className="tree-children">
                  {entityKindOrder.map((kind) => {
                    const count = entityKinds.find((item) => item.kind === kind)?.count || 0;
                    return <button key={kind} className={view === "entities" && entityKind === kind ? "active" : ""} onClick={() => selectEntityKind(kind)}><span>{entityKindLabels[kind]}</span><em>{count}</em></button>;
                  })}
                </div>
              </section>
              {visibleCategories.some((item) => ["voices", "sounds"].includes(item.id)) && <section className="tree-branch media-tree-branch">
                <div className="tree-parent"><Icon name="play" /><strong>声音</strong><em>{mediaKindCounts.reduce((count, item) => count + item.count, 0) || categoryCount(stats, audioFormats)}</em></div>
                <div className="tree-children">
                  {visibleCategories.filter((item) => ["voices", "sounds"].includes(item.id)).map((item) => <div className="tree-child-group" key={item.id}>
                    <button className={view === "assets" && assetCategory === item.id && !mediaGroup ? "active" : ""} onClick={() => selectAssetCategory(item.id)}><span>{item.label}</span><em>{mediaKindCounts.find((count) => count.kind === (item.id === "voices" ? "voice" : "sound"))?.count || 0}</em></button>
                    {view === "assets" && assetCategory === item.id && mediaGroups.filter((group) => group.group.endsWith(item.id === "voices" ? "_voice" : "_sound")).map((group) => <button className={`tree-grandchild ${mediaGroup === group.group ? "active" : ""}`} key={group.group} onClick={() => setMediaGroup(mediaGroup === group.group ? "" : group.group)}><span>{mediaGroupLabels[group.group] || group.group}</span><em>{group.count}</em></button>)}
                  </div>)}
                </div>
              </section>}
              {visibleCategories.some((item) => item.id === "animations") && <section className="tree-branch">
                <div className="tree-parent"><Icon name="image" /><strong>动画</strong><em>{categoryCount(stats, ["shp", "hva", "video"])}</em></div>
                <div className="tree-children">
                  <button className={view === "assets" && assetCategory === "animations" && !assetFormatTag ? "active" : ""} onClick={() => selectAssetCategory("animations")}><span>全部动画</span><em>{categoryCount(stats, ["shp", "hva", "video"])}</em></button>
                  {["shp", "hva", "video"].filter((formatName) => enabledFormats.includes(formatName)).map((formatName) => <button className={view === "assets" && assetCategory === "animations" && assetFormatTag === formatName ? "active" : ""} key={formatName} onClick={() => { setView("assets"); setAssetCategory("animations"); setAssetFormatTag(formatName); }}><span>{formatLabels[formatName]}</span><em>{stats.formats.find((item) => item.format === formatName)?.count || 0}</em></button>)}
                </div>
              </section>}
              {visibleCategories.filter((item) => !["voices", "sounds", "animations"].includes(item.id)).map((item) => (
                <button key={item.id} className={`tree-leaf ${view === "assets" && assetCategory === item.id ? "active" : ""}`} onClick={() => selectAssetCategory(item.id)}>
                  <span><Icon name={item.icon} />{item.label}</span><em>{categoryCount(stats, item.formats.filter((formatName) => enabledFormats.includes(formatName)))}</em>
                </button>
              ))}
            </nav>

          </aside>

          {view === "assets" ? <>{isMediaCategory ? <MediaListPanel
            items={mediaItems}
            total={mediaTotal}
            loading={mediaLoading}
            query={assetQuery}
            setQuery={setAssetQuery}
            groups={mediaGroups.filter((group) => group.group.endsWith(mediaKind === "voice" ? "_voice" : "_sound"))}
            selectedGroup={mediaGroup}
            setSelectedGroup={setMediaGroup}
            selectedId={selectedId}
            onSelect={(id) => { setSelectedId(id); setPlayingMediaId((current) => current === id ? "" : id); }}
            playingId={playingMediaId}
            layout={layout}
            setLayout={updateLayout}
            onLoadMore={loadMoreMedia}
          /> : <section className="asset-panel panel">
            <div className="asset-toolbar">
              <label className="search-box"><Icon name="search" /><input value={assetQuery} onChange={(event) => setAssetQuery(event.target.value)} placeholder="搜索名称或 CRC…" aria-label="搜索资产" />{assetQuery && <button onClick={() => setAssetQuery("")} aria-label="清除搜索"><Icon name="close" size={15} /></button>}</label>
              <span className="result-count">显示 {assets.length} / {total}</span>
              <LayoutToggle layout={layout} onChange={updateLayout} />
            </div>
            <div className="filter-strip">
              <div className="tag-filter" role="group" aria-label="按格式筛选">
                {categoryFormats.length > 1 && <button className={!assetFormatTag ? "active" : ""} onClick={() => setAssetFormatTag("")}>不限格式</button>}
                {categoryFormats.map((formatName) => <button key={formatName} className={assetFormatTag === formatName || categoryFormats.length === 1 ? "active" : ""} onClick={() => setAssetFormatTag(categoryFormats.length === 1 ? "" : formatName)}>
                  {formatLabels[formatName] || formatName.toUpperCase()}<em>{stats.formats.find((item) => item.format === formatName)?.count || 0}</em>
                </button>)}
              </div>
              <label className="sort-control"><span>排序</span><select value={assetSort} onChange={(event) => setAssetSort(event.target.value as AssetSort)}>
                <option value="name_asc">名称 A–Z</option>
                <option value="name_desc">名称 Z–A</option>
                <option value="size_desc">体积从大到小</option>
                <option value="size_asc">体积从小到大</option>
              </select></label>
            </div>
            {layout === "list" && <div className="list-heading"><span>资产</span><span>大小</span></div>}
            <div className={`asset-list ${layout === "grid" ? "asset-grid" : ""}`} tabIndex={0} aria-label="资产列表" onScroll={(event) => { const element = event.currentTarget; if (element.scrollHeight - element.scrollTop - element.clientHeight < 240) void loadMoreAssets(); }}>
              {layout === "list" ? assets.map((asset) => (
                <button key={asset.id} className={`asset-row ${selectedId === asset.id ? "selected" : ""}`} onClick={() => setSelectedId(asset.id)}>
                  <span className={`file-icon format-${asset.format}`}><Icon name={assetIcon(asset.format)} /></span>
                  <span className="asset-main"><strong>{asset.display_name}</strong><small>{formatLabels[asset.format] || asset.format.toUpperCase()}</small></span>
                  <span className="asset-size">{formatBytes(asset.size)}</span>
                  <Icon name="chevron" size={15} />
                </button>
              )) : assets.map((asset) => <AssetGridCard key={asset.id} asset={asset} selected={selectedId === asset.id} onSelect={setSelectedId} />)}
              {assets.length < total && <button className="load-more" disabled={assetPageLoading} onClick={() => void loadMoreAssets()}>{assetPageLoading ? "正在载入…" : `载入更多（剩余 ${(total - assets.length).toLocaleString("zh-CN")}）`}</button>}
              {assetPageLoading && assets.length === 0 && <div className="entity-loading"><div className="radar small"><span /></div><strong>正在载入资产…</strong></div>}
              {!assetPageLoading && assets.length === 0 && <div className="no-results"><Icon name="search" size={28} /><strong>没有匹配的资产</strong><button onClick={() => { setAssetQuery(""); setAssetFormatTag(""); }}>清除筛选</button></div>}
            </div>
          </section>}

          <DetailPanel
            asset={selected}
            metadata={metadata}
            textAsset={textAsset}
            textQuery={textQuery}
            setTextQuery={setTextQuery}
            frame={frame}
            setFrame={setFrame}
            playing={playing}
            setPlaying={setPlaying}
            palettes={palettes}
            paletteId={paletteId}
            setPaletteId={setPaletteId}
            playerColors={playerColors}
            previewUrl={previewUrl}
            associations={associations}
            onPopout={() => window.open(`/?detail=asset&asset_id=${encodeURIComponent(selectedId)}`, `ra2exp-asset-${selectedId}`, "popup=yes,width=560,height=900")}
          />
          </> : <>
            <EntityListPanel
              entities={visibleEntities}
              total={kindEntities.length}
              loading={entityLoading}
              query={entityQuery}
              setQuery={setEntityQuery}
              tags={entityTags}
              selectedTag={entityTag}
              setSelectedTag={setEntityTag}
              sort={entitySort}
              setSort={setEntitySort}
              selectedId={selectedEntityId}
              setSelectedId={setSelectedEntityId}
              sourceId={sourceId}
              countries={entityCountries}
              sides={entitySides}
              selectedCountry={entityCountry}
              setSelectedCountry={setEntityCountry}
              selectedSide={entitySide}
              setSelectedSide={setEntitySide}
              layout={layout}
              setLayout={updateLayout}
            />
            <EntityDetailPanel
              sourceId={sourceId}
              entity={selectedEntity}
              loading={entityDetailLoading}
              playerColors={playerColors}
              onPopout={() => window.open(`/?detail=entity&source_id=${encodeURIComponent(sourceId)}&entity_id=${encodeURIComponent(selectedEntityId)}`, `ra2exp-entity-${selectedEntityId}`, "popup=yes,width=560,height=900")}
            />
          </>}
        </main>
      )}

      {addOpen && <AddSourceDialog discoveries={discovery.candidates} busy={busy} onClose={() => setAddOpen(false)} onSubmit={async (path, name) => { await runAction(() => api.addSource(path, name), "资源目录已导入"); setAddOpen(false); }} />}
      {settingsOpen && <FormatSettingsDialog formats={stats.formats} enabled={enabledFormats} onChange={updateEnabledFormats} onClose={() => setSettingsOpen(false)} />}
      {error && <div className="toast error" role="alert"><Icon name="info" /><span>{error}</span><button onClick={() => setError("")} aria-label="关闭"><Icon name="close" size={15} /></button></div>}
      {notice && <div className="toast success" role="status"><span className="check">✓</span><span>{notice}</span></div>}
    </div>
  );
}

function EmptyLibrary({ busy, discoveries, onAdd, onImport }: {
  busy: boolean;
  discoveries: GameInstallation[];
  onAdd: () => void;
  onImport: (installation: GameInstallation) => void;
}) {
  return (
    <main className="empty-library">
      <div className="empty-visual" aria-hidden="true"><div className="disc"><span /><i /><b /></div><div className="scan-line" /></div>
      <h1>导入 RA2 游戏目录</h1>
      {discoveries.length > 0 && <div className="detected-installs">
        {discoveries.slice(0, 2).map((installation) => <button key={installation.path} disabled={busy} onClick={() => onImport(installation)}>
          <Icon name="folder" /><span><strong>{installation.edition}</strong><small>{installation.path}</small></span><em>导入</em>
        </button>)}
      </div>}
      <div className="empty-actions">
        <button className="button primary large" onClick={onAdd}><Icon name="folder" />导入游戏目录</button>
      </div>
    </main>
  );
}

function LayoutToggle({ layout, onChange }: { layout: LayoutMode; onChange: (layout: LayoutMode) => void }) {
  return (
    <div className="layout-toggle" role="group" aria-label="布局方式">
      <button className={layout === "list" ? "active" : ""} onClick={() => onChange("list")} aria-label="列表视图" title="列表视图"><Icon name="list" size={16} /></button>
      <button className={layout === "grid" ? "active" : ""} onClick={() => onChange("grid")} aria-label="网格视图" title="网格视图"><Icon name="grid" size={16} /></button>
    </div>
  );
}

function AssetGridCard({ asset, selected, onSelect }: { asset: Asset; selected: boolean; onSelect: (id: string) => void }) {
  const hasThumbnail = ["shp", "vxl", "tmp", "pcx", "pal", "map"].includes(asset.format);
  const isAudio = audioFormats.includes(asset.format);
  return (
    <button className={`asset-card ${selected ? "selected" : ""}`} onClick={() => onSelect(asset.id)}>
      <span className={`asset-card-preview format-${asset.format}`}>
        {hasThumbnail ? <img loading="lazy" src={api.previewUrl(asset.id, 0, "", 3)} alt="" onError={(event) => { event.currentTarget.hidden = true; }} />
          : isAudio ? <span className="audio-glyph" aria-hidden="true">{[4, 11, 7, 17, 12, 20, 9, 14, 5, 10].map((height, index) => <i key={index} style={{ height }} />)}</span>
            : <Icon name={assetIcon(asset.format)} size={32} />}
      </span>
      <span className="asset-card-copy"><strong title={asset.display_name}>{asset.display_name}</strong><small>{formatLabels[asset.format] || asset.format.toUpperCase()} · {formatBytes(asset.size)}</small></span>
    </button>
  );
}

function MediaListPanel({ items, total, loading, query, setQuery, groups, selectedGroup, setSelectedGroup, selectedId, onSelect, playingId, layout, setLayout, onLoadMore }: {
  items: MediaItem[];
  total: number;
  loading: boolean;
  query: string;
  setQuery: (value: string) => void;
  groups: Array<{ group: string; count: number }>;
  selectedGroup: string;
  setSelectedGroup: (value: string) => void;
  selectedId: string;
  onSelect: (id: string) => void;
  playingId: string;
  layout: LayoutMode;
  setLayout: (layout: LayoutMode) => void;
  onLoadMore: () => Promise<void>;
}) {
  const playing = items.find((item) => item.asset.id === playingId) || null;
  return (
    <section className="asset-panel media-panel panel">
      <div className="asset-toolbar">
        <label className="search-box"><Icon name="search" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索说明、台词、事件、单位或文件名…" aria-label="搜索声音" />{query && <button onClick={() => setQuery("")} aria-label="清除搜索"><Icon name="close" size={15} /></button>}</label>
        <span className="result-count">显示 {items.length} / {total}</span>
        <LayoutToggle layout={layout} onChange={setLayout} />
      </div>
      <div className="filter-strip">
        <div className="tag-filter" role="group" aria-label="按声音用途筛选">
          <button className={!selectedGroup ? "active" : ""} onClick={() => setSelectedGroup("")}>全部</button>
          {groups.map((group) => <button key={group.group} className={selectedGroup === group.group ? "active" : ""} onClick={() => setSelectedGroup(selectedGroup === group.group ? "" : group.group)}>{mediaGroupLabels[group.group] || group.group}<em>{group.count}</em></button>)}
        </div>
      </div>
      {layout === "list" && <div className="list-heading media-list-heading"><span>声音</span><span>关联</span></div>}
      <div className={`asset-list ${layout === "grid" ? "asset-grid media-grid" : ""}`} tabIndex={0} aria-label="声音列表" onScroll={(event) => { const element = event.currentTarget; if (element.scrollHeight - element.scrollTop - element.clientHeight < 240) void onLoadMore(); }}>
        {layout === "list" ? items.map((item) => <button key={item.asset.id} className={`asset-row media-row ${selectedId === item.asset.id ? "selected" : ""} ${playingId === item.asset.id ? "playing" : ""}`} onClick={() => onSelect(item.asset.id)}>
          <span className="file-icon format-audio"><Icon name={playingId === item.asset.id ? "pause" : "play"} /></span>
          <span className="asset-main"><strong>{item.description || item.asset.display_name}</strong><small>{item.asset.display_name}{item.texts.length > 1 ? ` · ${item.texts.length} 条文本` : ""}</small></span>
          <span className="media-links">{item.entities.slice(0, 2).map((entity) => entity.display_name).join(" · ") || item.events.slice(0, 2).join(" · ") || "未关联"}</span>
          <Icon name="chevron" size={15} />
        </button>) : items.map((item) => <button key={item.asset.id} className={`asset-card media-card ${selectedId === item.asset.id ? "selected" : ""} ${playingId === item.asset.id ? "playing" : ""}`} onClick={() => onSelect(item.asset.id)}>
          <span className="asset-card-preview format-audio"><span className="audio-glyph" aria-hidden="true">{[4, 11, 7, 17, 12, 20, 9, 14, 5, 10].map((height, index) => <i key={index} style={{ height }} />)}</span><Icon name={playingId === item.asset.id ? "pause" : "play"} size={20} /></span>
          <span className="asset-card-copy"><strong title={item.description || item.asset.display_name}>{item.description || item.asset.display_name}</strong><small>{item.asset.display_name}</small></span>
        </button>)}
        {items.length < total && <button className="load-more" disabled={loading} onClick={() => void onLoadMore()}>{loading ? "正在载入…" : `载入更多（剩余 ${(total - items.length).toLocaleString("zh-CN")}）`}</button>}
        {loading && items.length === 0 && <div className="entity-loading"><div className="radar small"><span /></div><strong>正在建立声音关联…</strong></div>}
        {!loading && items.length === 0 && <div className="no-results"><Icon name="search" size={28} /><strong>没有匹配的声音</strong><button onClick={() => { setQuery(""); setSelectedGroup(""); }}>清除筛选</button></div>}
      </div>
      {playing && <div className="media-now-playing"><div><Icon name="play" /><span><strong>{playing.description || playing.asset.display_name}</strong><small>{playing.asset.display_name}</small></span></div><audio key={playing.asset.id} controls autoPlay preload="metadata" src={api.mediaUrl(playing.asset.id)} onEnded={() => undefined} /></div>}
    </section>
  );
}

function EntityListPanel({ entities, total, loading, query, setQuery, tags, selectedTag, setSelectedTag, sort, setSort, selectedId, setSelectedId, sourceId, countries, sides, selectedCountry, setSelectedCountry, selectedSide, setSelectedSide, layout, setLayout }: {
  entities: EntitySummary[];
  total: number;
  loading: boolean;
  query: string;
  setQuery: (value: string) => void;
  tags: Array<{ tag: string; count: number }>;
  selectedTag: string;
  setSelectedTag: (value: string) => void;
  sort: EntitySort;
  setSort: (value: EntitySort) => void;
  selectedId: string;
  setSelectedId: (id: string) => void;
  sourceId: string;
  countries: Array<{ id: string; display_name: string; side: string; count: number }>;
  sides: Array<{ id: string; count: number }>;
  selectedCountry: string;
  setSelectedCountry: (value: string) => void;
  selectedSide: string;
  setSelectedSide: (value: string) => void;
  layout: LayoutMode;
  setLayout: (layout: LayoutMode) => void;
}) {
  return (
    <section className="asset-panel entity-panel panel">
      <div className="asset-toolbar">
        <label className="search-box"><Icon name="search" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索中文名、单位 ID、武器或阵营…" aria-label="搜索单位" />{query && <button onClick={() => setQuery("")} aria-label="清除搜索"><Icon name="close" size={15} /></button>}</label>
        <span className="result-count">显示 {entities.length} / {total}</span>
        <LayoutToggle layout={layout} onChange={setLayout} />
      </div>
      <div className="filter-strip">
        <div className="entity-filter-groups">
          <div className="tag-filter" role="group" aria-label="按阵营筛选">
            {sides.map((side) => <button key={side.id} className={selectedSide === side.id ? "active" : ""} onClick={() => setSelectedSide(selectedSide === side.id ? "" : side.id)}>{sideLabels[side.id] || side.id}<em>{side.count}</em></button>)}
          </div>
          <div className="tag-filter" role="group" aria-label="按国家筛选">
            {countries.filter((country) => !selectedSide || country.side === selectedSide).map((country) => <button key={country.id} className={selectedCountry === country.id ? "active" : ""} onClick={() => setSelectedCountry(selectedCountry === country.id ? "" : country.id)}>{country.display_name}<em>{country.count}</em></button>)}
          </div>
          <div className="tag-filter" role="group" aria-label="按单位特征筛选">
            {tags.map((item) => <button key={item.tag} className={selectedTag === item.tag ? "active" : ""} onClick={() => setSelectedTag(selectedTag === item.tag ? "" : item.tag)}>{entityTagLabels[item.tag]}<em>{item.count}</em></button>)}
          </div>
        </div>
        <label className="sort-control"><span>排序</span><select value={sort} onChange={(event) => setSort(event.target.value as EntitySort)}>
          <option value="name_asc">名称 A–Z</option>
          <option value="name_desc">名称 Z–A</option>
          <option value="cost_desc">造价从高到低</option>
          <option value="strength_desc">生命值从高到低</option>
        </select></label>
      </div>
      {layout === "list" && <div className="list-heading entity-list-heading"><span>单位</span><span>类型</span><span>数值</span></div>}
      <div className={`asset-list ${layout === "grid" ? "asset-grid entity-grid" : ""}`} tabIndex={0} aria-label="单位列表">
        {layout === "list" ? entities.map((entity) => (
          <button key={entity.id} className={`asset-row entity-row ${selectedId === entity.id ? "selected" : ""}`} onClick={() => setSelectedId(entity.id)}>
            <span className={`file-icon entity-icon ${entity.renderable ? "ready" : "missing"}`}><Icon name="unit" /></span>
            <span className="asset-main"><strong>{entity.display_name}</strong><small>{entity.id} → {entity.image}{entity.internal_name !== entity.display_name ? ` · ${entity.internal_name}` : ""}</small></span>
            <span className="entity-kind">{entityKindLabels[entity.kind]}</span>
            <span className="entity-stats"><strong>{entity.cost ? `$${entity.cost}` : "—"}</strong><small>{entity.strength ? `${entity.strength} HP` : entity.renderable ? `${entity.component_count} 个组件` : "缺少主体"}</small></span>
            <Icon name="chevron" size={15} />
          </button>
        )) : entities.map((entity) => <EntityGridCard key={entity.id} entity={entity} sourceId={sourceId} selected={selectedId === entity.id} onSelect={setSelectedId} />)}
        {loading && entities.length === 0 && <div className="entity-loading"><div className="radar small"><span /></div><strong>正在解析规则实体…</strong></div>}
        {!loading && entities.length === 0 && <div className="no-results"><Icon name="search" size={28} /><strong>没有匹配的单位</strong><button onClick={() => { setQuery(""); setSelectedTag(""); setSelectedCountry(""); setSelectedSide(""); }}>清除筛选</button></div>}
      </div>
    </section>
  );
}

function EntityGridCard({ entity, sourceId, selected, onSelect }: { entity: EntitySummary; sourceId: string; selected: boolean; onSelect: (id: string) => void }) {
  return (
    <button className={`asset-card entity-card ${selected ? "selected" : ""}`} onClick={() => onSelect(entity.id)}>
      <span className={`asset-card-preview entity-card-preview ${entity.renderable ? "ready" : "missing"}`}>
        {entity.renderable ? <img loading="lazy" src={api.entityPreviewUrl(sourceId, entity.id, { scale: 3 })} alt="" onError={(event) => { event.currentTarget.hidden = true; }} /> : <Icon name="unit" size={34} />}
      </span>
      <span className="asset-card-copy"><strong title={entity.display_name}>{entity.display_name}</strong><small>{entityKindLabels[entity.kind]} · {entity.cost ? `$${entity.cost}` : entity.component_count ? `${entity.component_count} 个组件` : "缺少主体"}</small></span>
    </button>
  );
}

function FrameGrid({ count, active, onSelect, urlFor }: { count: number; active: number; onSelect: (frame: number) => void; urlFor: (frame: number) => string }) {
  return <div className="frame-grid" aria-label="全部动画帧">{Array.from({ length: count }, (_, index) => <button type="button" key={index} className={active === index ? "active" : ""} onClick={() => onSelect(index)}><img loading="lazy" src={urlFor(index)} alt={`第 ${index + 1} 帧`} /><span>{index + 1}</span></button>)}</div>;
}

function EntityDetailPanel({ sourceId, entity, loading, playerColors, onPopout }: {
  sourceId: string;
  entity: GameEntity | null;
  loading: boolean;
  playerColors: PlayerColor[];
  onPopout?: () => void;
}) {
  const [frame, setFrame] = useState(0);
  const [facing, setFacing] = useState(0);
  const [playerColor, setPlayerColor] = useState("");
  const [playing, setPlaying] = useState(false);
  const [frameMode, setFrameMode] = useState<"sequence" | "grid">("sequence");
  const [previewFailed, setPreviewFailed] = useState(false);
  const frameCount = Math.max(1, entity?.preview.frame_count || 1);

  useEffect(() => {
    setFrame(0);
    setFacing(0);
    setPlayerColor("");
    setPlaying(false);
    setFrameMode("sequence");
    setPreviewFailed(false);
  }, [entity?.id]);

  useEffect(() => {
    if (!playing || frameCount < 2) return;
    const timer = window.setInterval(() => setFrame((current) => (current + 1) % frameCount), entity?.voxel ? 500 : 160);
    return () => window.clearInterval(timer);
  }, [playing, frameCount, entity?.voxel]);

  const previewUrl = useMemo(() => entity?.renderable ? api.entityPreviewUrl(
    sourceId,
    entity.id,
    { frame, facing, playerColor, scale: 4 },
  ) : "", [sourceId, entity, frame, facing, playerColor]);

  useEffect(() => setPreviewFailed(false), [previewUrl]);

  if (loading) return <aside className="detail-panel panel empty-detail"><div className="radar small"><span /></div><strong>正在读取单位详情…</strong></aside>;
  if (!entity) return <aside className="detail-panel panel empty-detail"><div className="empty-detail-icon"><Icon name="unit" size={30} /></div><strong>选择单位</strong></aside>;
  const rules = Object.entries(entity.rules).filter(([key]) => ruleLabels[key]);
  const dependencyGroups = [...new Set(entity.dependencies.map((item) => item.slot))].map(
    (slot) => ({ slot, items: entity.dependencies.filter((item) => item.slot === slot) }),
  );
  return (
    <aside className="detail-panel entity-detail panel">
      <div className="detail-title"><div><h2 title={entity.display_name}>{entity.display_name}</h2><small>{entity.id} · {entity.internal_name}</small></div>{onPopout && <button type="button" className="icon-button" onClick={onPopout} title="在独立窗口中打开" aria-label="在独立窗口中打开"><Icon name="popout" /></button>}</div>

      {entity.renderable ? <div className="preview-block entity-preview">
        {frameMode === "grid" && frameCount > 1
          ? <FrameGrid count={frameCount} active={frame} onSelect={setFrame} urlFor={(index) => api.entityPreviewUrl(sourceId, entity.id, { frame: index, facing, playerColor, scale: 3 })} />
          : entity.voxel
          ? <VoxelPreview url={api.entityModelUrl(sourceId, entity.id, { frame, playerColor })} label={entity.display_name} />
          : <div className="preview-stage shp"><div className="preview-rulers horizontal" /><div className="preview-rulers vertical" />{previewFailed ? <div className="preview-error"><Icon name="info" size={24} /><strong>预览生成失败</strong></div> : <img key={previewUrl} src={previewUrl} onError={() => setPreviewFailed(true)} alt={`${entity.display_name} 组合预览`} />}</div>}
        {frameCount > 1 && <div className="frame-controls">
          {frameMode === "sequence" && <><button className="play-button" onClick={() => setPlaying(!playing)} aria-label={playing ? "暂停" : "播放"}><Icon name={playing ? "pause" : "play"} size={16} /></button><input type="range" min="0" max={frameCount - 1} value={Math.min(frame, frameCount - 1)} onChange={(event) => setFrame(Number(event.target.value))} aria-label="当前动画帧" /><span>{String(frame + 1).padStart(2, "0")} <i>/</i> {String(frameCount).padStart(2, "0")}</span></>}
          <div className="frame-mode-toggle"><button className={frameMode === "sequence" ? "active" : ""} onClick={() => setFrameMode("sequence")} title="顺序播放"><Icon name="play" size={14} /></button><button className={frameMode === "grid" ? "active" : ""} onClick={() => { setPlaying(false); setFrameMode("grid"); }} title="全部帧"><Icon name="grid" size={14} /></button></div>
        </div>}
        <div className="entity-render-options compact-render-options">
          {!entity.voxel && entity.preview.supports_facing && <label><span>朝向</span><select value={facing} onChange={(event) => setFacing(Number(event.target.value))}>{Array.from({ length: 8 }, (_, index) => <option key={index} value={index}>{index * 45}°</option>)}</select></label>}
          {entity.preview.supports_player_color && <label><span>阵营色</span><select value={playerColor} onChange={(event) => setPlayerColor(event.target.value)}><option value="">原始色</option>{playerColors.map((color) => <option key={color.id} value={color.id}>{playerColorLabels[color.id] || color.id}</option>)}</select></label>}
        </div>
      </div> : <div className="unsupported-preview"><Icon name="unit" size={34} /><strong>缺少主体资产</strong></div>}

      {entity.media.length > 0 && <details className="entity-section compact-section" open>
        <summary><span>关联声音与动画</span><em>{entity.media.length}</em></summary>
        <div className="media-association-list">
          {entity.media.map((association) => <article key={`${association.kind}-${association.slot}-${association.event}`}>
            {association.samples.map((sample) => <div className="media-sample" key={`${association.event}-${sample.name}`}>
              <span className="media-sample-label"><b>{mediaSlotLabels[association.slot] || association.slot}</b><code>{association.event}</code><strong>{sample.name}</strong></span>
              {sample.asset && audioFormats.includes(sample.asset.format)
                && <audio controls preload="none" src={api.mediaUrl(sample.asset.id)} />}
              {sample.asset && !audioFormats.includes(sample.asset.format)
                && <a href={api.contentUrl(sample.asset.id)}>{sample.asset.display_name}</a>}
              {sample.text && <p>{sample.text}</p>}
            </div>)}
          </article>)}
        </div>
      </details>}

      <details className="entity-section compact-section entity-tag-section">
        <summary><span>标签</span><em>{2 + entity.countries.length + entity.sides.length}</em></summary>
        <div className="entity-tags" aria-label="单位资源摘要">
          <span>{entityKindLabels[entity.kind]}</span>
          <span>{entity.voxel ? "VXL 三维模型" : "SHP 帧动画"}</span>
          {entity.sides.map((side) => <span key={side}>{sideLabels[side] || side}</span>)}
          {entity.countries.map((country) => <span key={country}>{country}</span>)}
          <span>{entity.component_count} 个组件</span>
          {entity.preview.frame_count > 1 && <span>{entity.preview.frame_count} 个有效帧</span>}
          {entity.preview.source_frame_count !== undefined && entity.preview.source_frame_count !== entity.preview.frame_count && <span>源文件 {entity.preview.source_frame_count} 帧</span>}
          {entity.preview.voxel_count !== undefined && <span>{entity.preview.voxel_count.toLocaleString("zh-CN")} 体素</span>}
        </div>
      </details>

      {rules.length > 0 && <details className="entity-section compact-section entity-rules">
        <summary><span>规则属性</span><em>{rules.length}</em></summary>
        <div className="metadata"><dl>{rules.map(([key, value]) => <div key={key}><dt>{ruleLabels[key]}</dt><dd>{value}</dd></div>)}</dl></div>
      </details>}

      {dependencyGroups.length > 0 && <div className="entity-dependencies">
        <h3>战斗依赖</h3>
        <div className="dependency-groups">
          {dependencyGroups.map((group) => <details key={group.slot}>
            <summary><span>{dependencySlotLabels[group.slot]}</span><strong>{group.items[0]?.id}</strong><em>{group.items.length}</em></summary>
            <div className="dependency-compact">
              {group.items.map((dependency, index) => <article className={dependency.resolved ? "" : "unresolved"} key={`${dependency.kind}-${dependency.id}-${index}`}>
                <header><span>{dependencyKindLabels[dependency.kind]}</span><code>{dependency.id}</code>{!dependency.resolved && <em>缺少规则节</em>}</header>
                {Object.keys(dependency.properties).length > 0 && <div className="property-tags">{Object.entries(dependency.properties).map(([key, value]) => <span key={key} title={value}><b>{dependencyPropertyLabels[key] || key}</b>{value}</span>)}</div>}
              </article>)}
            </div>
          </details>)}
        </div>
      </div>}

      <details className="entity-section compact-section entity-components">
        <summary><span>资源文件</span><em>{entity.components.length}</em></summary>
        <div className="component-chips resource-file-list">
          {entity.components.map((component) => component.asset ? <a key={component.role} href={api.contentUrl(component.asset.id)} title={`${component.asset.virtual_path} · ${formatBytes(component.asset.size)}`}>
            <Icon name={assetIcon(component.asset.format)} size={14} />
            <strong>{componentRoleLabels[component.role] || component.role}</strong>
            <span>{component.asset.display_name}</span>
            <em>{formatBytes(component.asset.size)}</em>
          </a> : <span className="missing-component" key={component.role} title={component.expected_name}>
            <Icon name="file" size={14} />
            <strong>{componentRoleLabels[component.role] || component.role}</strong>
            <span>{component.expected_name}</span>
            <em>未找到</em>
          </span>)}
        </div>
      </details>
    </aside>
  );
}

function DetailPanel({ asset, metadata, textAsset, textQuery, setTextQuery, frame, setFrame, playing, setPlaying, palettes, paletteId, setPaletteId, playerColors, previewUrl, associations, onPopout }: {
  asset: Asset | null;
  metadata: AssetMetadata | null;
  textAsset: TextAsset | null;
  textQuery: string;
  setTextQuery: (value: string) => void;
  frame: number;
  setFrame: (frame: number | ((current: number) => number)) => void;
  playing: boolean;
  setPlaying: (playing: boolean) => void;
  palettes: Asset[];
  paletteId: string;
  setPaletteId: (id: string) => void;
  playerColors: PlayerColor[];
  previewUrl: string;
  associations: AssetAssociationPage | null;
  onPopout?: () => void;
}) {
  const [playerColor, setPlayerColor] = useState("");
  const [videoRequested, setVideoRequested] = useState(false);
  const [videoFailed, setVideoFailed] = useState(false);
  const [frameMode, setFrameMode] = useState<"sequence" | "grid">("sequence");
  useEffect(() => {
    setPlayerColor("");
    setVideoRequested(false);
    setVideoFailed(false);
    setFrameMode("sequence");
  }, [asset?.id]);
  if (!asset) return <aside className="detail-panel panel empty-detail"><div className="empty-detail-icon"><Icon name="image" size={30} /></div><strong>选择资产</strong></aside>;
  const canPreview = imageFormats.includes(asset.format);
  const isText = ["ini", "map", "text", "csf"].includes(asset.format);
  const isAudio = audioFormats.includes(asset.format);
  const isModel = ["vxl", "hva"].includes(asset.format);
  const frameCount = metadata?.frame_count || 1;
  const activeFrame = metadata?.frames?.[frame];
  const activeLimb = metadata?.limbs?.[frame];
  const hasFrameControl = ["shp", "tmp", "hva"].includes(asset.format) && frameCount > 1;
  const canChoosePalette = ["shp", "vxl", "hva", "tmp"].includes(asset.format) && palettes.length > 0;
  return (
    <aside className="detail-panel panel">
      <div className="detail-title"><div><span className="format-pill">{formatLabels[asset.format] || asset.format.toUpperCase()}</span><h2 title={asset.display_name}>{asset.display_name}</h2></div><div className="detail-actions">{onPopout && <button type="button" className="icon-button" onClick={onPopout} title="在独立窗口中打开" aria-label="在独立窗口中打开"><Icon name="popout" /></button>}<a className="icon-button" href={api.contentUrl(asset.id)} title="导出原始文件" aria-label="导出原始文件"><Icon name="download" /></a></div></div>

      {isModel && <div className="preview-block">
        {frameMode === "grid" && asset.format === "hva" && frameCount > 1
          ? <FrameGrid count={frameCount} active={frame} onSelect={setFrame} urlFor={(index) => api.previewUrl(asset.id, index, paletteId, 3, playerColor)} />
          : <VoxelPreview url={api.assetModelUrl(asset.id, frame, playerColor, paletteId)} label={asset.display_name} />}
        {asset.format === "hva" && hasFrameControl && <div className="frame-controls">
          {frameMode === "sequence" && <><button className="play-button" onClick={() => setPlaying(!playing)} aria-label={playing ? "暂停" : "播放"}><Icon name={playing ? "pause" : "play"} size={16} /></button><input type="range" min="0" max={frameCount - 1} value={Math.min(frame, frameCount - 1)} onChange={(event) => setFrame(Number(event.target.value))} aria-label="当前动画帧" /><span>{String(frame + 1).padStart(2, "0")} <i>/</i> {String(frameCount).padStart(2, "0")}</span></>}
          <div className="frame-mode-toggle"><button className={frameMode === "sequence" ? "active" : ""} onClick={() => setFrameMode("sequence")} title="顺序播放"><Icon name="play" size={14} /></button><button className={frameMode === "grid" ? "active" : ""} onClick={() => { setPlaying(false); setFrameMode("grid"); }} title="全部帧"><Icon name="grid" size={14} /></button></div>
        </div>}
      </div>}

      {canPreview && (
        <div className="preview-block">
          {frameMode === "grid" && asset.format === "shp" && frameCount > 1
            ? <FrameGrid count={frameCount} active={frame} onSelect={setFrame} urlFor={(index) => api.previewUrl(asset.id, index, paletteId, 3, playerColor)} />
            : <div className={`preview-stage ${asset.format}`}><div className="preview-rulers horizontal" /><div className="preview-rulers vertical" /><img key={previewUrl} src={previewUrl} alt={`${asset.display_name} 预览`} /></div>}
          {hasFrameControl && <div className="frame-controls">
            {frameMode === "sequence" && <><button className="play-button" disabled={asset.format === "tmp"} onClick={() => setPlaying(!playing)} aria-label={playing ? "暂停" : "播放"}><Icon name={playing ? "pause" : assetIcon(asset.format)} size={16} /></button><input type="range" min="0" max={Math.max(0, frameCount - 1)} value={Math.min(frame, frameCount - 1)} onChange={(event) => setFrame(Number(event.target.value))} aria-label={asset.format === "vxl" ? "当前部件" : asset.format === "tmp" ? "当前地块" : "当前帧"} /><span>{String(frame + 1).padStart(2, "0")} <i>/</i> {String(frameCount).padStart(2, "0")}</span></>}
            {asset.format === "shp" && <div className="frame-mode-toggle"><button className={frameMode === "sequence" ? "active" : ""} onClick={() => setFrameMode("sequence")} title="顺序播放"><Icon name="play" size={14} /></button><button className={frameMode === "grid" ? "active" : ""} onClick={() => { setPlaying(false); setFrameMode("grid"); }} title="全部帧"><Icon name="grid" size={14} /></button></div>}
          </div>}
        </div>
      )}

      {isAudio && <div className="audio-preview"><div><Icon name="play" size={25} /><span><strong>音频预览</strong><small>{metadata?.audio_codec || (metadata?.audio_format === 17 ? "IMA ADPCM → PCM16" : "PCM 音频")}</small></span></div><audio controls preload="metadata" src={api.mediaUrl(asset.id)}>浏览器不支持音频播放。</audio></div>}

      {asset.format === "video" && <div className="video-preview">
        {videoRequested && !videoFailed
          ? <video controls autoPlay preload="metadata" src={api.videoUrl(asset.id)} onLoadedData={() => setVideoFailed(false)} onError={() => setVideoFailed(true)}>浏览器不支持视频播放。</video>
          : <button type="button" className="button primary" onClick={() => { setVideoFailed(false); setVideoRequested(true); }}><Icon name="play" />{videoFailed ? "重试转换" : "转换并播放"}</button>}
        {videoFailed && <strong className="video-error">视频转换失败</strong>}
      </div>}

      {isText && <div className="text-preview">
        <label><Icon name="search" size={14} /><input value={textQuery} onChange={(event) => setTextQuery(event.target.value)} placeholder="在当前文件中筛选…" /></label>
        <pre>{textAsset?.text || "正在读取文本…"}</pre>
        {textAsset && <small>显示 {textAsset.returned_lines} / {textAsset.line_count} 行{textAsset.truncated ? " · 已截断" : ""}</small>}
      </div>}

      {associations && associations.items.length > 0 && <div className="asset-associations">
        <h3>关联事件</h3>
        <div>{associations.items.map((item, index) => <article key={`${item.scope}-${item.event}-${item.slot}-${index}`}>
          <span>{mediaSlotLabels[item.slot] || item.slot}</span>
          <strong>{item.entity?.display_name || item.event}</strong>
          {item.entity && <code>{item.event}</code>}
          {item.text && <p>{item.text}</p>}
        </article>)}</div>
      </div>}

      {!canPreview && !isText && !isAudio && !isModel && asset.format !== "video" && <div className="unsupported-preview"><Icon name={assetIcon(asset.format)} size={34} /><strong>{formatLabels[asset.format] || asset.format.toUpperCase()}</strong></div>}

      {(canChoosePalette || isModel) && <div className="entity-render-options asset-render-options">
        {isModel && <label><span>阵营色</span><select value={playerColor} onChange={(event) => setPlayerColor(event.target.value)}><option value="">原始色</option>{playerColors.map((color) => <option key={color.id} value={color.id}>{playerColorLabels[color.id] || color.id}</option>)}</select></label>}
        {canChoosePalette && <label><span>配色表</span><select value={paletteId} onChange={(event) => setPaletteId(event.target.value)}><option value="">自动</option>{palettes.map((palette) => <option key={palette.id} value={palette.id}>{palette.display_name}</option>)}</select></label>}
      </div>}

      <div className="metadata">
        <h3>资产信息</h3>
        <dl>
          <div><dt>文件大小</dt><dd>{formatBytes(asset.size)}</dd></div>
          {metadata?.width !== undefined && metadata?.height !== undefined && <div><dt>{asset.format === "map" ? "地图尺寸" : "画布 / 地块"}</dt><dd>{metadata.width} × {metadata.height}{asset.format === "map" ? " 格" : " px"}</dd></div>}
          {metadata?.theater && <div><dt>地图环境</dt><dd>{metadata.theater}</dd></div>}
          {metadata?.object_counts && <div><dt>地图对象</dt><dd>{Object.entries(metadata.object_counts).map(([kind, count]) => `${mapObjectLabels[kind] || kind} ${count}`).join(" · ")}</dd></div>}
          {metadata?.template_width !== undefined && <div><dt>模板网格</dt><dd>{metadata.template_width} × {metadata.template_height} · {metadata.tile_count} 个地块</dd></div>}
          {metadata?.frame_count !== undefined && <div><dt>{asset.format === "vxl" ? "部件数" : "帧 / 槽位"}</dt><dd>{metadata.frame_count}</dd></div>}
          {activeFrame && <div><dt>当前帧</dt><dd>{activeFrame.width} × {activeFrame.height} · 压缩 {activeFrame.compression}</dd></div>}
          {activeLimb && <div><dt>当前部件</dt><dd>{activeLimb.name} · {activeLimb.size.join("×")} · {activeLimb.voxel_count.toLocaleString("zh-CN")} 体素</dd></div>}
          {metadata?.voxel_count !== undefined && <div><dt>总体素</dt><dd>{metadata.voxel_count.toLocaleString("zh-CN")}</dd></div>}
          {metadata?.section_count !== undefined && <div><dt>节 / 段</dt><dd>{metadata.section_count}{metadata.section_names?.length ? ` · ${metadata.section_names.slice(0, 3).join(", ")}` : ""}</dd></div>}
          {metadata?.label_count !== undefined && <div><dt>CSF 文本</dt><dd>{metadata.label_count} 标签 · {metadata.string_count} 字符串</dd></div>}
          {metadata?.entry_count !== undefined && <div><dt>配置结构</dt><dd>{metadata.section_count} 节 · {metadata.entry_count} 项</dd></div>}
          {metadata?.encoding && <div><dt>文本编码</dt><dd>{metadata.encoding}</dd></div>}
          {metadata?.duration_seconds !== undefined && <div><dt>音频</dt><dd>{formatDuration(metadata.duration_seconds)} · {metadata.sample_rate?.toLocaleString("zh-CN")} Hz · {metadata.bits_per_sample} bit</dd></div>}
          <div><dt>来源</dt><dd>{asset.storage_kind === "loose" ? "松散文件" : asset.storage_kind === "bag" ? "音频包" : "MIX 归档"}</dd></div>
          {asset.crc !== null && <div><dt>CRC</dt><dd className="mono">{crcLabel(asset.crc)}</dd></div>}
          <div><dt>识别</dt><dd>{asset.confidence === "name" ? "名称库匹配" : asset.confidence === "content" ? "内容探测" : asset.confidence === "filename" ? "文件名" : asset.confidence === "index" ? "音频索引" : "未知"}</dd></div>
        </dl>
      </div>
      <a className="button export-button" href={api.contentUrl(asset.id)}><Icon name="download" />导出原始资产</a>
    </aside>
  );
}

function FormatSettingsDialog({ formats, enabled, onChange, onClose }: {
  formats: Stats["formats"];
  enabled: string[];
  onChange: (formats: string[]) => void;
  onClose: () => void;
}) {
  const enabledSet = new Set(enabled);
  const available = formats.map((item) => item.format);
  function toggle(formatName: string) {
    onChange(enabledSet.has(formatName)
      ? enabled.filter((item) => item !== formatName)
      : [...enabled, formatName]);
  }
  useEffect(() => {
    const close = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [onClose]);
  return (
    <div className="dialog-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="dialog format-settings" role="dialog" aria-modal="true" aria-labelledby="format-settings-title">
        <div className="dialog-header"><div className="dialog-icon"><Icon name="settings" /></div><div><h2 id="format-settings-title">显示与载入</h2></div><button type="button" onClick={onClose} aria-label="关闭"><Icon name="close" /></button></div>
        <div className="format-settings-actions">
          <button type="button" onClick={() => onChange(available.filter((item) => defaultVisibleFormats.includes(item)))}>常用素材</button>
          <button type="button" onClick={() => onChange(available)}>全部启用</button>
        </div>
        <div className="format-checks">
          {formats.map((item) => <label key={item.format} className={enabledSet.has(item.format) ? "checked" : ""}>
            <input type="checkbox" checked={enabledSet.has(item.format)} onChange={() => toggle(item.format)} />
            <span className={`file-icon format-${item.format}`}><Icon name={assetIcon(item.format)} size={15} /></span>
            <strong>{formatLabels[item.format] || item.format.toUpperCase()}</strong>
            <em>{item.count.toLocaleString("zh-CN")}</em>
          </label>)}
        </div>
        <div className="dialog-actions"><button type="button" className="button primary" onClick={onClose}>完成</button></div>
      </section>
    </div>
  );
}

function AddSourceDialog({ discoveries, busy, onClose, onSubmit }: { discoveries: GameInstallation[]; busy: boolean; onClose: () => void; onSubmit: (path: string, name: string) => Promise<void> }) {
  const [path, setPath] = useState("");
  const [name, setName] = useState("");
  function submit(event: FormEvent) { event.preventDefault(); if (path.trim()) void onSubmit(path.trim(), name.trim()); }
  useEffect(() => {
    const close = (event: KeyboardEvent) => event.key === "Escape" && !busy && onClose();
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [busy, onClose]);
  return (
    <div className="dialog-backdrop" onMouseDown={(event) => event.target === event.currentTarget && !busy && onClose()}>
      <form className="dialog" onSubmit={submit}>
        <div className="dialog-header"><div className="dialog-icon"><Icon name="folder" /></div><div><h2>添加资源目录</h2></div><button type="button" onClick={onClose} disabled={busy} aria-label="关闭"><Icon name="close" /></button></div>
        {discoveries.length > 0 && <div className="dialog-discoveries"><span>自动发现</span>{discoveries.map((installation) => <button type="button" key={installation.path} onClick={() => { setPath(installation.path); setName(installation.name); }}><Icon name="folder" size={15} /><span><strong>{installation.edition}</strong><small>{installation.provider} · {installation.path}</small></span><em>选择</em></button>)}</div>}
        <label><span>目录路径 <b>必填</b></span><input autoFocus value={path} onChange={(event) => setPath(event.target.value)} placeholder="例如 D:\SteamLibrary\steamapps\common\Command & Conquer Red Alert II" /></label>
        <label><span>显示名称 <em>可选</em></span><input value={name} onChange={(event) => setName(event.target.value)} placeholder="例如 Steam 原版" /></label>
        <div className="dialog-actions"><button type="button" className="button ghost" disabled={busy} onClick={onClose}>取消</button><button type="submit" className="button primary" disabled={busy || !path.trim()}>{busy ? "正在扫描…" : "添加并扫描"}</button></div>
      </form>
    </div>
  );
}

function DetachedEntityDetail({ sourceId, entityId }: { sourceId: string; entityId: string }) {
  const [entity, setEntity] = useState<GameEntity | null>(null);
  const [colors, setColors] = useState<PlayerColor[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    Promise.all([api.entity(sourceId, entityId), api.playerColors()])
      .then(([nextEntity, nextColors]) => {
        setEntity(nextEntity);
        setColors(nextColors);
        document.title = `${nextEntity.display_name} · RA2 Explorer`;
      })
      .catch((reason: Error) => setError(reason.message));
  }, [sourceId, entityId]);
  return <main className="detached-shell">{error ? <div className="detached-error">{error}</div> : <EntityDetailPanel sourceId={sourceId} entity={entity} loading={!entity} playerColors={colors} />}</main>;
}

function DetachedAssetDetail({ assetId }: { assetId: string }) {
  const [asset, setAsset] = useState<Asset | null>(null);
  const [metadata, setMetadata] = useState<AssetMetadata | null>(null);
  const [associations, setAssociations] = useState<AssetAssociationPage | null>(null);
  const [textAsset, setTextAsset] = useState<TextAsset | null>(null);
  const [palettes, setPalettes] = useState<Asset[]>([]);
  const [colors, setColors] = useState<PlayerColor[]>([]);
  const [textQuery, setTextQuery] = useState("");
  const [frame, setFrame] = useState(0);
  const [paletteId, setPaletteId] = useState("");
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    api.asset(assetId)
      .then(async (nextAsset) => {
        const [nextMetadata, nextAssociations, nextPalettes, nextColors] = await Promise.all([
          api.metadata(assetId),
          api.assetAssociations(assetId).catch(() => null),
          api.palettes(nextAsset.source_id),
          api.playerColors(),
        ]);
        setAsset(nextAsset);
        setMetadata(nextMetadata);
        setAssociations(nextAssociations);
        setPalettes(nextPalettes);
        setColors(nextColors);
        document.title = `${nextAsset.display_name} · RA2 Explorer`;
      })
      .catch((reason: Error) => setError(reason.message));
  }, [assetId]);
  useEffect(() => {
    if (!asset || !["ini", "map", "text", "csf"].includes(asset.format)) return;
    const timer = window.setTimeout(() => api.text(asset.id, textQuery).then(setTextAsset).catch(() => undefined), textQuery ? 180 : 0);
    return () => window.clearTimeout(timer);
  }, [asset, textQuery]);
  useEffect(() => {
    if (!playing || !asset || !["shp", "hva"].includes(asset.format) || !metadata?.frame_count || metadata.frame_count < 2) return;
    const timer = window.setInterval(() => setFrame((current) => (current + 1) % metadata.frame_count!), asset.format === "hva" ? 350 : 140);
    return () => window.clearInterval(timer);
  }, [playing, asset, metadata]);
  const previewUrl = asset && imageFormats.includes(asset.format)
    ? api.previewUrl(asset.id, frame, paletteId, asset.format === "pcx" ? 1 : asset.format === "shp" ? 5 : 4)
    : "";
  return <main className="detached-shell">{error ? <div className="detached-error">{error}</div> : <DetailPanel asset={asset} metadata={metadata} textAsset={textAsset} textQuery={textQuery} setTextQuery={setTextQuery} frame={frame} setFrame={setFrame} playing={playing} setPlaying={setPlaying} palettes={palettes} paletteId={paletteId} setPaletteId={setPaletteId} playerColors={colors} previewUrl={previewUrl} associations={associations} />}</main>;
}

function App() {
  const params = new URLSearchParams(window.location.search);
  const detail = params.get("detail");
  if (detail === "entity" && params.get("source_id") && params.get("entity_id")) {
    return <DetachedEntityDetail sourceId={params.get("source_id")!} entityId={params.get("entity_id")!} />;
  }
  if (detail === "asset" && params.get("asset_id")) {
    return <DetachedAssetDetail assetId={params.get("asset_id")!} />;
  }
  return <ExplorerApp />;
}

export default App;
