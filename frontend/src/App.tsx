import { FormEvent, ReactNode, useEffect, useMemo, useState } from "react";

import {
  api,
  Asset,
  ReferenceStatus,
  ShpMetadata,
  Source,
  Stats,
} from "./api";

type IconName =
  | "archive"
  | "chevron"
  | "close"
  | "download"
  | "file"
  | "folder"
  | "image"
  | "info"
  | "pause"
  | "play"
  | "refresh"
  | "search"
  | "settings"
  | "spark"
  | "swatch";

function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, ReactNode> = {
    archive: <><path d="M4 7.5h16v12H4z" /><path d="M3 4.5h18v3H3zM9 11h6" /></>,
    chevron: <path d="m9 18 6-6-6-6" />,
    close: <><path d="m6 6 12 12M18 6 6 18" /></>,
    download: <><path d="M12 3v12m0 0 4-4m-4 4-4-4" /><path d="M5 20h14" /></>,
    file: <><path d="M6 3h8l4 4v14H6z" /><path d="M14 3v5h5" /></>,
    folder: <path d="M3 6h7l2 2h9v11H3z" />,
    image: <><rect x="3" y="4" width="18" height="16" rx="2" /><circle cx="9" cy="10" r="2" /><path d="m4 17 5-4 4 3 3-2 4 3" /></>,
    info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v6m0-10h.01" /></>,
    pause: <><path d="M9 7v10M15 7v10" /></>,
    play: <path d="m9 7 8 5-8 5z" />,
    refresh: <><path d="M20 11a8 8 0 0 0-14.8-4L3 10" /><path d="M3 5v5h5M4 13a8 8 0 0 0 14.8 4L21 14" /><path d="M21 19v-5h-5" /></>,
    search: <><circle cx="11" cy="11" r="7" /><path d="m16 16 5 5" /></>,
    settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.03 1.56V21h-4v-.08A1.7 1.7 0 0 0 9 19.37a1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.63 15a1.7 1.7 0 0 0-1.55-1.03H3v-4h.08A1.7 1.7 0 0 0 4.63 9a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.83-2.83.06.06A1.7 1.7 0 0 0 9 4.63a1.7 1.7 0 0 0 1-1.55V3h4v.08A1.7 1.7 0 0 0 15 4.63a1.7 1.7 0 0 0 1.88-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0 0 19.37 9a1.7 1.7 0 0 0 1.55 1.03H21v4h-.08A1.7 1.7 0 0 0 19.4 15Z" /></>,
    spark: <><path d="m12 3 1.1 4.2L17 9l-3.9 1.8L12 15l-1.1-4.2L7 9l3.9-1.8z" /><path d="m19 15 .6 2.4L22 18.5l-2.4 1.1L19 22l-.6-2.4-2.4-1.1 2.4-1.1z" /></>,
    swatch: <><path d="M4 4h6v16H4zM10 7h5v13h-5zM15 10h5v10h-5z" /><path d="M7 16h.01M12.5 16h.01M17.5 16h.01" /></>,
  };
  return (
    <svg className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <g stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</g>
    </svg>
  );
}

const formatLabels: Record<string, string> = {
  shp: "SHP 动画",
  pal: "PAL 调色板",
  mix: "MIX 归档",
  ini: "INI 配置",
  csf: "CSF 文本",
  vxl: "VXL 模型",
  hva: "HVA 动画",
  wav: "WAV 音频",
  unknown: "其他",
};

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(value < 10 * 1024 ? 1 : 0)} KB`;
  return `${(value / 1024 ** 2).toFixed(1)} MB`;
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
  if (format === "shp") return "image";
  if (format === "pal") return "swatch";
  if (format === "mix") return "archive";
  return "file";
}

function App() {
  const [sources, setSources] = useState<Source[]>([]);
  const [sourceId, setSourceId] = useState("");
  const [assets, setAssets] = useState<Asset[]>([]);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState<Stats>({ total_assets: 0, formats: [] });
  const [palettes, setPalettes] = useState<Asset[]>([]);
  const [query, setQuery] = useState("");
  const [format, setFormat] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [selected, setSelected] = useState<Asset | null>(null);
  const [shp, setShp] = useState<ShpMetadata | null>(null);
  const [frame, setFrame] = useState(0);
  const [paletteId, setPaletteId] = useState("");
  const [playing, setPlaying] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [reference, setReference] = useState<ReferenceStatus | null>(null);

  const activeSource = sources.find((item) => item.id === sourceId) ?? null;

  async function refreshSources(preferredId?: string) {
    const next = await api.sources();
    setSources(next);
    const candidate = preferredId || sourceId;
    setSourceId(next.some((item) => item.id === candidate) ? candidate : next[0]?.id || "");
  }

  useEffect(() => {
    Promise.all([api.sources(), api.referenceStatus()])
      .then(([nextSources, nextReference]) => {
        setSources(nextSources);
        setSourceId(nextSources[0]?.id || "");
        setReference(nextReference);
      })
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!sourceId) {
      setAssets([]);
      setStats({ total_assets: 0, formats: [] });
      setPalettes([]);
      setSelectedId("");
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      Promise.all([api.assets(sourceId, query, format), api.stats(sourceId), api.palettes(sourceId)])
        .then(([page, nextStats, nextPalettes]) => {
          if (cancelled) return;
          setAssets(page.items);
          setTotal(page.total);
          setStats(nextStats);
          setPalettes(nextPalettes);
          setSelectedId((current) =>
            page.items.some((asset) => asset.id === current)
              ? current
              : page.items.find((asset) => asset.format === "shp")?.id || page.items[0]?.id || "",
          );
        })
        .catch((reason: Error) => !cancelled && setError(reason.message));
    }, query ? 180 : 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [sourceId, query, format]);

  useEffect(() => {
    setFrame(0);
    setPlaying(false);
    setShp(null);
    setPaletteId("");
    if (!selectedId) {
      setSelected(null);
      return;
    }
    let cancelled = false;
    api.asset(selectedId)
      .then((asset) => {
        if (cancelled) return;
        setSelected(asset);
        if (asset.format === "shp") {
          api.shp(asset.id).then((metadata) => !cancelled && setShp(metadata)).catch((reason: Error) => !cancelled && setError(reason.message));
        }
      })
      .catch((reason: Error) => !cancelled && setError(reason.message));
    return () => { cancelled = true; };
  }, [selectedId]);

  useEffect(() => {
    if (!playing || !shp || shp.frame_count < 2) return;
    const timer = window.setInterval(() => setFrame((current) => (current + 1) % shp.frame_count), 140);
    return () => window.clearInterval(timer);
  }, [playing, shp]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(""), 3200);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const previewUrl = useMemo(() => {
    if (!selected || !["shp", "pal"].includes(selected.format)) return "";
    return api.previewUrl(selected.id, frame, paletteId, selected.format === "pal" ? 3 : 5);
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

  async function syncNames() {
    setBusy(true);
    setError("");
    try {
      const status = await api.syncNames();
      setReference({ ...status, available: true, manifest_valid: true });
      setNotice(`文件名库已同步：${status.name_count?.toLocaleString("zh-CN") || "完成"} 条`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "同步失败");
    } finally {
      setBusy(false);
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
          <div><strong>RA2 Explorer</strong><small>本地资产工作台</small></div>
        </div>
        <div className="topbar-actions">
          {activeSource && <span className={`source-status ${activeSource.state}`}><i />{stateLabel(activeSource.state)}</span>}
          <button className="button ghost compact" onClick={() => setAddOpen(true)}><Icon name="folder" />添加目录</button>
          <button className="button primary compact" disabled={busy || !activeSource} onClick={() => activeSource && runAction(() => api.scanSource(activeSource.id), "目录索引已更新")}><Icon name="refresh" />重新扫描</button>
        </div>
      </header>

      {sources.length === 0 ? (
        <EmptyLibrary busy={busy} onDemo={() => runAction(api.createDemo, "演示资产库已创建")} onAdd={() => setAddOpen(true)} />
      ) : (
        <main className="workspace">
          <aside className="source-panel panel">
            <section className="source-heading">
              <span className="eyebrow">当前资料库</span>
              <label className="source-select-wrap">
                <select value={sourceId} onChange={(event) => setSourceId(event.target.value)} aria-label="选择资料库">
                  {sources.map((source) => <option key={source.id} value={source.id}>{source.name}</option>)}
                </select>
                <Icon name="chevron" size={15} />
              </label>
              {activeSource && <p className="source-path" title={activeSource.root_path}>{activeSource.root_path}</p>}
            </section>

            <section className="summary-grid" aria-label="索引统计">
              <div><strong>{stats.total_assets.toLocaleString("zh-CN")}</strong><span>资产</span></div>
              <div><strong>{activeSource?.archive_count.toLocaleString("zh-CN")}</strong><span>归档</span></div>
            </section>

            <nav className="format-nav" aria-label="资产格式">
              <button className={!format ? "active" : ""} onClick={() => setFormat("")}><span><Icon name="archive" />全部资产</span><em>{stats.total_assets}</em></button>
              {stats.formats.map((item) => (
                <button key={item.format} className={format === item.format ? "active" : ""} onClick={() => setFormat(item.format)}>
                  <span><Icon name={assetIcon(item.format)} />{formatLabels[item.format] || item.format.toUpperCase()}</span><em>{item.count}</em>
                </button>
              ))}
            </nav>

            <section className="reference-card">
              <div className="reference-title"><Icon name="settings" /><span>文件名识别库</span></div>
              <p>{reference?.available ? `${reference.name_count?.toLocaleString("zh-CN") || "扩展"} 个已知名称` : "当前仅使用内置基础名称"}</p>
              <button disabled={busy} onClick={syncNames}>{reference?.available ? "重新同步" : "同步成熟名称库"}<Icon name="chevron" size={13} /></button>
            </section>
          </aside>

          <section className="asset-panel panel">
            <div className="asset-toolbar">
              <label className="search-box"><Icon name="search" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索名称、路径或 CRC…" aria-label="搜索资产" />{query && <button onClick={() => setQuery("")} aria-label="清除搜索"><Icon name="close" size={15} /></button>}</label>
              <span className="result-count">显示 {assets.length} / {total}</span>
            </div>
            <div className="list-heading"><span>资产</span><span>位置</span><span>大小</span></div>
            <div className="asset-list">
              {assets.map((asset) => (
                <button key={asset.id} className={`asset-row ${selectedId === asset.id ? "selected" : ""}`} onClick={() => setSelectedId(asset.id)}>
                  <span className={`file-icon format-${asset.format}`}><Icon name={assetIcon(asset.format)} /></span>
                  <span className="asset-main"><strong>{asset.display_name}</strong><small>{asset.virtual_path}</small></span>
                  <span className="asset-location">{asset.storage_kind === "loose" ? "松散文件" : asset.archive_path || "MIX"}</span>
                  <span className="asset-size">{formatBytes(asset.size)}</span>
                  <Icon name="chevron" size={15} />
                </button>
              ))}
              {assets.length === 0 && <div className="no-results"><Icon name="search" size={28} /><strong>没有匹配的资产</strong><span>尝试清除关键词或切换格式。</span><button onClick={() => { setQuery(""); setFormat(""); }}>清除筛选</button></div>}
            </div>
          </section>

          <DetailPanel asset={selected} shp={shp} frame={frame} setFrame={setFrame} playing={playing} setPlaying={setPlaying} palettes={palettes} paletteId={paletteId} setPaletteId={setPaletteId} previewUrl={previewUrl} />
        </main>
      )}

      {addOpen && <AddSourceDialog busy={busy} onClose={() => setAddOpen(false)} onSubmit={async (path, name) => { await runAction(() => api.addSource(path, name), "资源目录已导入"); setAddOpen(false); }} />}
      {error && <div className="toast error" role="alert"><Icon name="info" /><span>{error}</span><button onClick={() => setError("")} aria-label="关闭"><Icon name="close" size={15} /></button></div>}
      {notice && <div className="toast success" role="status"><span className="check">✓</span><span>{notice}</span></div>}
    </div>
  );
}

function EmptyLibrary({ busy, onDemo, onAdd }: { busy: boolean; onDemo: () => void; onAdd: () => void }) {
  return (
    <main className="empty-library">
      <div className="empty-visual" aria-hidden="true"><div className="disc"><span /><i /><b /></div><div className="scan-line" /></div>
      <span className="eyebrow">欢迎来到本地资料库</span>
      <h1>把尘封的战场资产<br />重新带到眼前</h1>
      <p>只读扫描你合法安装的《红色警戒 2》目录，浏览 MIX、SHP 与 PAL；游戏文件始终留在本机。</p>
      <div className="empty-actions">
        <button className="button primary large" onClick={onAdd}><Icon name="folder" />导入游戏目录</button>
        <button className="button ghost large" disabled={busy} onClick={onDemo}><Icon name="spark" />{busy ? "正在创建…" : "先看合成演示"}</button>
      </div>
      <div className="feature-strip"><span><b>01</b>本地只读索引</span><span><b>02</b>嵌套 MIX 解析</span><span><b>03</b>SHP 逐帧预览</span></div>
    </main>
  );
}

function DetailPanel({ asset, shp, frame, setFrame, playing, setPlaying, palettes, paletteId, setPaletteId, previewUrl }: {
  asset: Asset | null;
  shp: ShpMetadata | null;
  frame: number;
  setFrame: (frame: number | ((current: number) => number)) => void;
  playing: boolean;
  setPlaying: (playing: boolean) => void;
  palettes: Asset[];
  paletteId: string;
  setPaletteId: (id: string) => void;
  previewUrl: string;
}) {
  if (!asset) return <aside className="detail-panel panel empty-detail"><div className="empty-detail-icon"><Icon name="image" size={30} /></div><strong>选择一个资产</strong><span>在这里查看预览与技术信息</span></aside>;
  const canPreview = asset.format === "shp" || asset.format === "pal";
  const activeFrame = shp?.frames[frame];
  return (
    <aside className="detail-panel panel">
      <div className="detail-title"><div><span className="format-pill">{formatLabels[asset.format] || asset.format.toUpperCase()}</span><h2 title={asset.display_name}>{asset.display_name}</h2></div><a className="icon-button" href={api.contentUrl(asset.id)} title="导出原始文件" aria-label="导出原始文件"><Icon name="download" /></a></div>
      {canPreview ? (
        <div className="preview-block">
          <div className={`preview-stage ${asset.format}`}><div className="preview-rulers horizontal" /><div className="preview-rulers vertical" /><img key={previewUrl} src={previewUrl} alt={`${asset.display_name} 预览`} /></div>
          {asset.format === "shp" && (
            <div className="frame-controls">
              <button className="play-button" disabled={!shp || shp.frame_count < 2} onClick={() => setPlaying(!playing)} aria-label={playing ? "暂停" : "播放"}><Icon name={playing ? "pause" : "play"} size={16} /></button>
              <input type="range" min="0" max={Math.max(0, (shp?.frame_count || 1) - 1)} value={frame} onChange={(event) => setFrame(Number(event.target.value))} aria-label="当前帧" />
              <span>{String(frame + 1).padStart(2, "0")} <i>/</i> {String(shp?.frame_count || 1).padStart(2, "0")}</span>
            </div>
          )}
        </div>
      ) : <div className="unsupported-preview"><Icon name={assetIcon(asset.format)} size={34} /><strong>首版暂不渲染此格式</strong><span>仍可核对索引信息并导出原始文件。</span></div>}

      {asset.format === "shp" && palettes.length > 0 && (
        <label className="palette-select"><span>渲染调色板</span><select value={paletteId} onChange={(event) => setPaletteId(event.target.value)}><option value="">自动选择</option>{palettes.map((palette) => <option key={palette.id} value={palette.id}>{palette.display_name}</option>)}</select></label>
      )}

      <div className="metadata">
        <h3>资产信息</h3>
        <dl>
          <div><dt>尺寸</dt><dd>{shp ? `${shp.width} × ${shp.height} px` : formatBytes(asset.size)}</dd></div>
          {shp && <div><dt>帧数</dt><dd>{shp.frame_count}</dd></div>}
          {activeFrame && <div><dt>当前帧</dt><dd>{activeFrame.width} × {activeFrame.height} · 压缩 {activeFrame.compression}</dd></div>}
          <div><dt>来源</dt><dd>{asset.storage_kind === "loose" ? "松散文件" : "MIX 归档"}</dd></div>
          <div><dt>CRC</dt><dd className="mono">{crcLabel(asset.crc)}</dd></div>
          <div><dt>识别</dt><dd>{asset.confidence === "name" ? "名称库匹配" : asset.confidence === "content" ? "内容探测" : asset.confidence === "filename" ? "文件名" : "未知"}</dd></div>
        </dl>
      </div>
      <div className="path-card"><span>虚拟路径</span><code title={asset.virtual_path}>{asset.virtual_path}</code></div>
      <a className="button export-button" href={api.contentUrl(asset.id)}><Icon name="download" />导出原始资产</a>
    </aside>
  );
}

function AddSourceDialog({ busy, onClose, onSubmit }: { busy: boolean; onClose: () => void; onSubmit: (path: string, name: string) => Promise<void> }) {
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
        <div className="dialog-header"><div className="dialog-icon"><Icon name="folder" /></div><div><span className="eyebrow">只读扫描</span><h2>添加资源目录</h2></div><button type="button" onClick={onClose} disabled={busy} aria-label="关闭"><Icon name="close" /></button></div>
        <p>粘贴 Steam、EA App 或 Mod 的本机目录。扫描只会读取文件并将索引写入 RA2 Explorer 自己的数据目录。</p>
        <label><span>目录路径 <b>必填</b></span><input autoFocus value={path} onChange={(event) => setPath(event.target.value)} placeholder="例如 D:\SteamLibrary\steamapps\common\Command & Conquer Red Alert II" /></label>
        <label><span>显示名称 <em>可选</em></span><input value={name} onChange={(event) => setName(event.target.value)} placeholder="例如 Steam 原版" /></label>
        <div className="dialog-note"><Icon name="info" size={16} /><span>RA2 Explorer 不包含商业游戏文件；请先通过 Steam 或 EA App 合法安装。</span></div>
        <div className="dialog-actions"><button type="button" className="button ghost" disabled={busy} onClick={onClose}>取消</button><button type="submit" className="button primary" disabled={busy || !path.trim()}>{busy ? "正在扫描…" : "添加并扫描"}</button></div>
      </form>
    </div>
  );
}

export default App;
