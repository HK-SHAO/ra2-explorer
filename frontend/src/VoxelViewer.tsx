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
  viewHeight: number;
  updateProjection: (() => void) | null;
  resetView: (() => void) | null;
  render: (() => void) | null;
}

export function VoxelViewer({ url, label }: { url: string; label: string }) {
  const mountRef = useRef<HTMLDivElement>(null);
  const engineRef = useRef<ViewerEngine | null>(null);
  const [data, setData] = useState<VoxelSceneData | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

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

      const render = () => renderer.render(scene, camera);
      controls.addEventListener("change", render);

      const engine: ViewerEngine = {
        scene,
        camera,
        renderer,
        controls,
        model: null,
        grid: null,
        fitBounds: null,
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
  }, [label]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    fetch(url, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) {
          const body = (await response.json().catch(() => ({}))) as { detail?: string };
          throw new Error(body.detail || `模型加载失败（${response.status}）`);
        }
        return response.json() as Promise<VoxelSceneData>;
      })
      .then((scene) => {
        if (![1, 2, 3, 4].includes(scene.version) || !Array.isArray(scene.voxels)) {
          throw new Error("模型数据版本不受支持");
        }
        setData(scene);
        setLoading(false);
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setData(null);
        setLoading(false);
        setError(reason instanceof Error ? reason.message : "模型加载失败");
      });
    return () => controller.abort();
  }, [url]);

  useEffect(() => {
    const engine = engineRef.current;
    if (!engine || !data) return;
    disposeModel(engine);

    const geometry = new THREE.BoxGeometry(1, 1, 1);
    const material = data.lighting === "westwood_vpl"
      ? new THREE.MeshBasicMaterial({ color: 0xffffff })
      : new THREE.MeshLambertMaterial({ color: 0xffffff, flatShading: true });
    const model = new THREE.InstancedMesh(geometry, material, data.voxels.length);
    model.instanceMatrix.setUsage(THREE.StaticDrawUsage);
    const transform = new THREE.Object3D();
    const color = new THREE.Color();
    const box = new THREE.Box3().makeEmpty();
    const voxelMinimum = new THREE.Vector3();
    const voxelMaximum = new THREE.Vector3();
    data.voxels.forEach((voxel, index) => {
      const [x, y, z, size, red, green, blue] = voxel;
      const safeSize = Math.max(0.000_001, size);
      const halfSize = safeSize / 2;
      transform.position.set(x, z, y);
      transform.scale.setScalar(safeSize);
      transform.updateMatrix();
      model.setMatrixAt(index, transform.matrix);
      color.setRGB(red / 255, green / 255, blue / 255, THREE.SRGBColorSpace);
      model.setColorAt(index, color);
      voxelMinimum.set(x - halfSize, z - halfSize, y - halfSize);
      voxelMaximum.set(x + halfSize, z + halfSize, y + halfSize);
      box.expandByPoint(voxelMinimum);
      box.expandByPoint(voxelMaximum);
    });
    model.instanceMatrix.needsUpdate = true;
    if (model.instanceColor) model.instanceColor.needsUpdate = true;
    model.computeBoundingSphere();
    engine.scene.add(model);
    engine.model = model;

    if (box.isEmpty()) {
      const minimum = data.bounds.min;
      const maximum = data.bounds.max;
      box.set(
        new THREE.Vector3(minimum[0], minimum[2], minimum[1]),
        new THREE.Vector3(maximum[0], maximum[2], maximum[1]),
      );
    }
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
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
    engine.fitBounds = box.clone();

    const resetView = () => {
      const radius = Math.max(diameter / 2, 0.05);
      const distance = Math.max(radius * 4, 1);
      const direction = new THREE.Vector3(1, 1, 1).normalize();
      engine.camera.near = Math.max(distance - radius * 2.5, 0.000_1);
      engine.camera.far = Math.max(distance + radius * 4, 100);
      engine.camera.position.copy(center).addScaledVector(direction, distance);
      engine.camera.up.set(0, 1, 0);
      engine.camera.lookAt(center);
      engine.camera.updateMatrixWorld(true);
      engine.camera.zoom = 1;
      engine.controls.target.copy(center);
      engine.controls.update();
      engine.updateProjection?.();
      engine.render?.();
    };
    engine.resetView = resetView;
    resetView();
  }, [data]);

  return (
    <div className="voxel-viewer" aria-busy={loading}>
      <div ref={mountRef} className="voxel-canvas" />
      {data && !loading && (
        <button type="button" className="voxel-reset" onClick={() => engineRef.current?.resetView?.()}>
          重置视角
        </button>
      )}
      {loading && <div className="voxel-status">正在载入模型…</div>}
      {error && <div className="voxel-status error">{error}</div>}
    </div>
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
