import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

export interface VoxelSceneData {
  version: number;
  frame: number;
  frame_count: number;
  part_count: number;
  voxel_count: number;
  visible_voxel_count?: number;
  lighting?: "westwood_vpl" | "lambert";
  bounds: { min: number[]; max: number[] };
  voxels: number[][];
}

interface ViewerEngine {
  scene: THREE.Scene;
  camera: THREE.OrthographicCamera;
  renderer: THREE.WebGLRenderer;
  controls: OrbitControls;
  model: THREE.InstancedMesh | null;
  grid: THREE.GridHelper | null;
  fitBounds: THREE.Box3 | null;
  viewKey: string | null;
  viewHeight: number;
  updateProjection: (() => void) | null;
  resetView: (() => void) | null;
  render: (() => void) | null;
}

type PreviewAngle = 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7;

const MODEL_RESPONSE_CACHE = "ra2exp-model-scenes-v5";
const MAX_MEMORY_SCENES = 12;
const MAX_MEMORY_VOXELS = 180_000;
const MAX_PERSISTENT_RESPONSES = 260;
const sceneCache = new Map<string, VoxelSceneData>();
const sceneRequests = new Map<string, Promise<VoxelSceneData>>();
let cachedVoxelCount = 0;
let modelPreloadEnabled = false;

export function configureVoxelPreload(enabled: boolean) {
  modelPreloadEnabled = enabled;
  if (enabled) return;
  sceneCache.clear();
  sceneRequests.clear();
  cachedVoxelCount = 0;
  if ("caches" in window) void window.caches.delete(MODEL_RESPONSE_CACHE);
}

export async function preloadVoxelScenes(urls: string[], signal?: AbortSignal) {
  if (!modelPreloadEnabled || signal?.aborted) return;
  const uniqueUrls = Array.from(new Set(urls.filter(Boolean)));
  const parsed = uniqueUrls.slice(0, 3);
  await Promise.all(parsed.map((url) => requestVoxelScene(url, signal).catch(() => undefined)));
  for (const url of uniqueUrls.slice(parsed.length)) {
    if (signal?.aborted || !modelPreloadEnabled) return;
    await cacheVoxelResponse(url, signal).catch(() => undefined);
  }
}

export function VoxelViewer({ url, label, viewKey, previewAngle, onPreviewAngleChange, onLoadSettled }: {
  url: string;
  label: string;
  viewKey: string;
  previewAngle: PreviewAngle;
  onPreviewAngleChange?: (angle: PreviewAngle) => void;
  onLoadSettled?: () => void;
}) {
  const mountRef = useRef<HTMLDivElement>(null);
  const engineRef = useRef<ViewerEngine | null>(null);
  const previewAngleRef = useRef(previewAngle);
  const reportedPreviewAngleRef = useRef<PreviewAngle | null>(null);
  const onPreviewAngleChangeRef = useRef(onPreviewAngleChange);
  const onLoadSettledRef = useRef(onLoadSettled);
  const [loadedScene, setLoadedScene] = useState<{ data: VoxelSceneData; viewKey: string } | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  previewAngleRef.current = previewAngle;
  onPreviewAngleChangeRef.current = onPreviewAngleChange;
  onLoadSettledRef.current = onLoadSettled;

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;
    let resizeObserver: ResizeObserver | null = null;
    let resizeFrame = 0;
    let lastWidth = 0;
    let lastHeight = 0;
    try {
      const scene = new THREE.Scene();
      const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.001, 10_000);
      const renderer = new THREE.WebGLRenderer({
        alpha: true,
        antialias: true,
        powerPreference: "high-performance",
      });
      renderer.outputColorSpace = THREE.SRGBColorSpace;
      renderer.toneMapping = THREE.NoToneMapping;
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      renderer.domElement.tabIndex = 0;
      renderer.domElement.setAttribute("aria-label", `${label} 交互式三维模型`);
      mount.appendChild(renderer.domElement);

      const ambientLight = new THREE.AmbientLight(0xd8dde5, 0.72);
      const keyLight = new THREE.DirectionalLight(0xfff0d1, 1.08);
      keyLight.position.set(-4, 7, 5);
      scene.add(ambientLight, keyLight);

      const controls = new OrbitControls(camera, renderer.domElement);
      controls.enableDamping = false;
      controls.screenSpacePanning = true;
      controls.minZoom = 0.35;
      controls.maxZoom = 12;

      let lastPreviewAngle = -1;
      const render = () => {
        renderer.render(scene, camera);
        const offsetX = camera.position.x - controls.target.x;
        const offsetZ = camera.position.z - controls.target.z;
        const sector = Math.round(Math.atan2(offsetX, offsetZ) / (Math.PI / 4));
        const currentPreviewAngle = ((sector % 8) + 8) % 8 as PreviewAngle;
        if (currentPreviewAngle !== lastPreviewAngle) {
          lastPreviewAngle = currentPreviewAngle;
          reportedPreviewAngleRef.current = currentPreviewAngle;
          onPreviewAngleChangeRef.current?.(currentPreviewAngle);
        }
      };
      controls.addEventListener("change", render);

      const engine: ViewerEngine = {
        scene,
        camera,
        renderer,
        controls,
        model: null,
        grid: null,
        fitBounds: null,
        viewKey: null,
        viewHeight: 2,
        updateProjection: null,
        resetView: null,
        render,
      };
      engineRef.current = engine;

      const updateProjection = () => {
        const width = Math.max(1, mount.clientWidth);
        const height = Math.max(1, mount.clientHeight);
        if (engine.fitBounds) {
          engine.viewHeight = fittedViewHeight(
            engine.fitBounds,
            camera,
            width / height,
          );
        }
        const halfHeight = Math.max(engine.viewHeight, 0.001) / 2;
        const halfWidth = halfHeight * (width / height);
        camera.left = -halfWidth;
        camera.right = halfWidth;
        camera.top = halfHeight;
        camera.bottom = -halfHeight;
        camera.updateProjectionMatrix();
      };
      engine.updateProjection = updateProjection;
      const resize = () => {
        window.cancelAnimationFrame(resizeFrame);
        resizeFrame = window.requestAnimationFrame(() => {
          const width = Math.max(1, mount.clientWidth);
          const height = Math.max(1, mount.clientHeight);
          if (width === lastWidth && height === lastHeight) return;
          lastWidth = width;
          lastHeight = height;
          renderer.setSize(width, height, false);
          updateProjection();
          render();
        });
      };
      resizeObserver = new ResizeObserver(resize);
      resizeObserver.observe(mount);
      resize();

      render();
    } catch {
      setError("当前浏览器无法创建 WebGL 视图");
    }

    return () => {
      resizeObserver?.disconnect();
      window.cancelAnimationFrame(resizeFrame);
      const engine = engineRef.current;
      if (!engine) return;
      disposeModel(engine);
      engine.controls.dispose();
      engine.renderer.dispose();
      engine.renderer.forceContextLoss();
      engine.renderer.domElement.remove();
      engineRef.current = null;
    };
  }, []);

  useEffect(() => {
    engineRef.current?.renderer.domElement.setAttribute(
      "aria-label",
      `${label} 交互式三维模型`,
    );
  }, [label]);

  useEffect(() => {
    if (reportedPreviewAngleRef.current === previewAngle) {
      reportedPreviewAngleRef.current = null;
      return;
    }
    engineRef.current?.resetView?.();
  }, [previewAngle]);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setLoading(true);
    setError("");
    requestVoxelScene(url, controller.signal)
      .then((scene) => {
        if (!active) return;
        setLoadedScene({ data: scene, viewKey });
      })
      .catch((reason: unknown) => {
        if (!active || controller.signal.aborted) return;
        setLoadedScene(null);
        setLoading(false);
        setError(reason instanceof Error ? reason.message : "模型加载失败");
        onLoadSettledRef.current?.();
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [url, viewKey]);

  useEffect(() => {
    const engine = engineRef.current;
    if (!loadedScene) return;
    if (!engine) {
      setLoading(false);
      onLoadSettledRef.current?.();
      return;
    }
    const { data, viewKey: loadedViewKey } = loadedScene;
    const preserveView = engine.viewKey === loadedViewKey && engine.fitBounds !== null;
    const preservedBounds = preserveView ? engine.fitBounds?.clone() || null : null;
    disposeModel(engine);

    const geometry = data.lighting === "westwood_vpl"
      ? unlitVoxelGeometry()
      : new THREE.BoxGeometry(1, 1, 1);
    const material = data.lighting === "westwood_vpl"
      ? new THREE.MeshBasicMaterial({ color: 0xffffff })
      : new THREE.MeshLambertMaterial({ color: 0xffffff, flatShading: true });
    const model = new THREE.InstancedMesh(geometry, material, data.voxels.length);
    model.instanceMatrix.setUsage(THREE.StaticDrawUsage);
    const matrices = model.instanceMatrix.array as Float32Array;
    const colors = new Float32Array(data.voxels.length * 3);
    const color = new THREE.Color();
    const colorCache = new Map<number, readonly [number, number, number]>();
    data.voxels.forEach((voxel, index) => {
      const [x, y, z, size, red, green, blue] = voxel;
      const safeSize = Math.max(0.000_001, size);
      const matrixOffset = index * 16;
      matrices[matrixOffset] = safeSize;
      matrices[matrixOffset + 5] = safeSize;
      matrices[matrixOffset + 10] = safeSize;
      matrices[matrixOffset + 12] = x;
      matrices[matrixOffset + 13] = z;
      matrices[matrixOffset + 14] = y;
      matrices[matrixOffset + 15] = 1;

      const colorKey = (red << 16) | (green << 8) | blue;
      let linear = colorCache.get(colorKey);
      if (!linear) {
        color.setRGB(red / 255, green / 255, blue / 255, THREE.SRGBColorSpace);
        linear = [color.r, color.g, color.b];
        colorCache.set(colorKey, linear);
      }
      const colorOffset = index * 3;
      colors[colorOffset] = linear[0];
      colors[colorOffset + 1] = linear[1];
      colors[colorOffset + 2] = linear[2];
    });
    model.instanceMatrix.needsUpdate = true;
    model.instanceColor = new THREE.InstancedBufferAttribute(colors, 3);
    model.instanceColor.needsUpdate = true;
    const box = sceneBounds(data.bounds);
    model.boundingBox = box.clone();
    model.boundingSphere = box.getBoundingSphere(new THREE.Sphere());
    engine.scene.add(model);
    engine.model = model;
    engine.fitBounds = preservedBounds || box.clone();
    engine.viewKey = loadedViewKey;
    const center = engine.fitBounds.getCenter(new THREE.Vector3());
    const size = engine.fitBounds.getSize(new THREE.Vector3());
    const diameter = Math.max(size.length(), 0.1);
    const gridSize = Math.max(size.x, size.z, diameter * 0.75, 0.5) * 1.7;
    const grid = new THREE.GridHelper(gridSize, 12, 0x424852, 0x292d34);
    grid.position.set(center.x, box.min.y - Math.max(diameter * 0.012, 0.002), center.z);
    const gridMaterials = Array.isArray(grid.material) ? grid.material : [grid.material];
    gridMaterials.forEach((item) => {
      item.transparent = true;
      item.opacity = 0.46;
    });
    engine.scene.add(grid);
    engine.grid = grid;
    const resetView = () => {
      const radius = Math.max(diameter / 2, 0.05);
      const distance = Math.max(radius * 4, 1);
      const angle = previewAngleRef.current * (Math.PI / 4);
      const direction = new THREE.Vector3(Math.sin(angle), 1, Math.cos(angle)).normalize();
      engine.camera.near = Math.max(distance - radius * 2.5, 0.000_1);
      engine.camera.far = Math.max(distance + radius * 4, 100);
      engine.camera.position.copy(center).addScaledVector(direction, distance);
      engine.camera.up.set(0, 1, 0);
      engine.camera.lookAt(center);
      engine.camera.updateMatrixWorld(true);
      engine.camera.zoom = 1;
      engine.controls.target.copy(center);
      engine.updateProjection?.();
      if (!engine.controls.update()) engine.render?.();
    };
    engine.resetView = resetView;
    if (preserveView) {
      engine.updateProjection?.();
      engine.render?.();
    } else {
      resetView();
    }
    setLoading(false);
    onLoadSettledRef.current?.();
  }, [loadedScene]);

  return (
    <div className="voxel-viewer" aria-busy={loading}>
      <div ref={mountRef} className="voxel-canvas" />
      {loadedScene && !loading && (
        <button type="button" className="voxel-reset" onClick={() => engineRef.current?.resetView?.()} title="重置到显示设置中的默认角度">
          重置视角
        </button>
      )}
      {loading && <div className="voxel-status">正在载入模型…</div>}
      {error && <div className="voxel-status error">{error}</div>}
    </div>
  );
}

async function requestVoxelScene(url: string, signal?: AbortSignal) {
  if (modelPreloadEnabled) {
    const cached = sceneCache.get(url);
    if (cached) {
      sceneCache.delete(url);
      sceneCache.set(url, cached);
      return cached;
    }
    let pending = sceneRequests.get(url);
    if (!pending) {
      pending = fetchVoxelScene(url).then((scene) => {
        if (modelPreloadEnabled) cacheVoxelScene(url, scene);
        return scene;
      }).finally(() => sceneRequests.delete(url));
      sceneRequests.set(url, pending);
    }
    const scene = await pending;
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    return scene;
  }
  return fetchVoxelScene(url, signal);
}

async function fetchVoxelScene(url: string, signal?: AbortSignal) {
  const response = await modelResponse(url, signal);
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: string };
    throw new Error(body.detail || `模型加载失败（${response.status}）`);
  }
  const scene = await response.json() as VoxelSceneData;
  if (![1, 2, 3, 4].includes(scene.version) || !Array.isArray(scene.voxels)) {
    throw new Error("模型数据版本不受支持");
  }
  return scene;
}

async function modelResponse(url: string, signal?: AbortSignal) {
  if (!modelPreloadEnabled || !url.includes("r=") || !("caches" in window)) {
    return fetch(url, { signal });
  }
  const cache = await window.caches.open(MODEL_RESPONSE_CACHE);
  const cached = await cache.match(url);
  if (cached) return cached;
  const response = await fetch(url, { signal });
  if (response.ok && modelPreloadEnabled) {
    void cache.put(url, response.clone())
      .then(() => prunePersistentCache(cache))
      .catch(() => undefined);
  }
  return response;
}

async function cacheVoxelResponse(url: string, signal?: AbortSignal) {
  if (!url.includes("r=") || !("caches" in window)) return;
  const cache = await window.caches.open(MODEL_RESPONSE_CACHE);
  if (await cache.match(url)) return;
  const response = await fetch(url, { signal });
  if (!response.ok || !modelPreloadEnabled || signal?.aborted) return;
  await cache.put(url, response);
  await prunePersistentCache(cache);
}

async function prunePersistentCache(cache: Cache) {
  const keys = await cache.keys();
  const excess = keys.length - MAX_PERSISTENT_RESPONSES;
  if (excess > 0) await Promise.all(keys.slice(0, excess).map((key) => cache.delete(key)));
}

function cacheVoxelScene(url: string, scene: VoxelSceneData) {
  const previous = sceneCache.get(url);
  if (previous) cachedVoxelCount -= previous.voxels.length;
  sceneCache.delete(url);
  sceneCache.set(url, scene);
  cachedVoxelCount += scene.voxels.length;
  while (
    sceneCache.size > 1
    && (sceneCache.size > MAX_MEMORY_SCENES || cachedVoxelCount > MAX_MEMORY_VOXELS)
  ) {
    const oldestKey = sceneCache.keys().next().value as string | undefined;
    if (!oldestKey) break;
    const oldest = sceneCache.get(oldestKey);
    sceneCache.delete(oldestKey);
    cachedVoxelCount -= oldest?.voxels.length || 0;
  }
}

function unlitVoxelGeometry() {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute([
    -0.5, -0.5, -0.5,
    0.5, -0.5, -0.5,
    0.5, 0.5, -0.5,
    -0.5, 0.5, -0.5,
    -0.5, -0.5, 0.5,
    0.5, -0.5, 0.5,
    0.5, 0.5, 0.5,
    -0.5, 0.5, 0.5,
  ], 3));
  geometry.setIndex([
    0, 2, 1, 0, 3, 2,
    4, 5, 6, 4, 6, 7,
    0, 1, 5, 0, 5, 4,
    3, 7, 6, 3, 6, 2,
    1, 2, 6, 1, 6, 5,
    0, 4, 7, 0, 7, 3,
  ]);
  geometry.computeBoundingBox();
  geometry.computeBoundingSphere();
  return geometry;
}

function sceneBounds(bounds: VoxelSceneData["bounds"]) {
  const minimum = bounds.min;
  const maximum = bounds.max;
  return new THREE.Box3(
    new THREE.Vector3(minimum[0], minimum[2], minimum[1]),
    new THREE.Vector3(maximum[0], maximum[2], maximum[1]),
  );
}

function disposeModel(engine: ViewerEngine) {
  if (engine.model) {
    engine.scene.remove(engine.model);
    engine.model.geometry.dispose();
    const materials = Array.isArray(engine.model.material)
      ? engine.model.material
      : [engine.model.material];
    materials.forEach((material) => material.dispose());
    engine.model = null;
  }
  if (engine.grid) {
    engine.scene.remove(engine.grid);
    engine.grid.geometry.dispose();
    const materials = Array.isArray(engine.grid.material)
      ? engine.grid.material
      : [engine.grid.material];
    materials.forEach((material) => material.dispose());
    engine.grid = null;
  }
  engine.fitBounds = null;
  engine.resetView = null;
}

function fittedViewHeight(
  bounds: THREE.Box3,
  camera: THREE.OrthographicCamera,
  aspect: number,
) {
  camera.updateMatrixWorld(true);
  const { min, max } = bounds;
  const corners = [
    new THREE.Vector3(min.x, min.y, min.z),
    new THREE.Vector3(min.x, min.y, max.z),
    new THREE.Vector3(min.x, max.y, min.z),
    new THREE.Vector3(min.x, max.y, max.z),
    new THREE.Vector3(max.x, min.y, min.z),
    new THREE.Vector3(max.x, min.y, max.z),
    new THREE.Vector3(max.x, max.y, min.z),
    new THREE.Vector3(max.x, max.y, max.z),
  ];
  let minimumX = Number.POSITIVE_INFINITY;
  let maximumX = Number.NEGATIVE_INFINITY;
  let minimumY = Number.POSITIVE_INFINITY;
  let maximumY = Number.NEGATIVE_INFINITY;
  corners.forEach((corner) => {
    corner.applyMatrix4(camera.matrixWorldInverse);
    minimumX = Math.min(minimumX, corner.x);
    maximumX = Math.max(maximumX, corner.x);
    minimumY = Math.min(minimumY, corner.y);
    maximumY = Math.max(maximumY, corner.y);
  });
  const projectedWidth = Math.max(0.001, maximumX - minimumX);
  const projectedHeight = Math.max(0.001, maximumY - minimumY);
  return Math.max(projectedHeight, projectedWidth / Math.max(aspect, 0.1), 0.1) * 1.16;
}
