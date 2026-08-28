import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

export interface VoxelSceneData {
  version: number;
  frame: number;
  frame_count: number;
  part_count: number;
  voxel_count: number;
  bounds: { min: number[]; max: number[] };
  voxels: number[][];
}

interface ViewerEngine {
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  renderer: THREE.WebGLRenderer;
  controls: OrbitControls;
  model: THREE.InstancedMesh | null;
  grid: THREE.GridHelper | null;
  resetView: (() => void) | null;
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
    let animationFrame = 0;
    let resizeObserver: ResizeObserver | null = null;
    try {
      const scene = new THREE.Scene();
      scene.fog = new THREE.FogExp2(0x101217, 0.035);
      const camera = new THREE.PerspectiveCamera(38, 1, 0.001, 10_000);
      const renderer = new THREE.WebGLRenderer({
        alpha: true,
        antialias: true,
        powerPreference: "high-performance",
      });
      renderer.outputColorSpace = THREE.SRGBColorSpace;
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      renderer.domElement.tabIndex = 0;
      renderer.domElement.setAttribute("aria-label", `${label} 交互式三维模型`);
      mount.appendChild(renderer.domElement);

      const controls = new OrbitControls(camera, renderer.domElement);
      controls.enableDamping = true;
      controls.dampingFactor = 0.075;
      controls.screenSpacePanning = true;
      controls.minDistance = 0.05;
      controls.maxDistance = 1_000;

      scene.add(new THREE.HemisphereLight(0xcdd9ee, 0x29231f, 2.1));
      const keyLight = new THREE.DirectionalLight(0xffffff, 2.4);
      keyLight.position.set(4, 7, 5);
      scene.add(keyLight);
      const fillLight = new THREE.DirectionalLight(0xb4c7ff, 1.1);
      fillLight.position.set(-5, 2, -3);
      scene.add(fillLight);

      const engine: ViewerEngine = {
        scene,
        camera,
        renderer,
        controls,
        model: null,
        grid: null,
        resetView: null,
      };
      engineRef.current = engine;

      const resize = () => {
        const width = Math.max(1, mount.clientWidth);
        const height = Math.max(1, mount.clientHeight);
        renderer.setSize(width, height, false);
        camera.aspect = width / height;
        camera.updateProjectionMatrix();
      };
      resizeObserver = new ResizeObserver(resize);
      resizeObserver.observe(mount);
      resize();

      const animate = () => {
        controls.update();
        renderer.render(scene, camera);
        animationFrame = requestAnimationFrame(animate);
      };
      animate();
    } catch {
      setError("当前浏览器无法创建 WebGL 视图");
    }

    return () => {
      cancelAnimationFrame(animationFrame);
      resizeObserver?.disconnect();
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
        if (scene.version !== 1 || !Array.isArray(scene.voxels)) {
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
    const material = new THREE.MeshStandardMaterial({
      metalness: 0.03,
      roughness: 0.74,
    });
    const model = new THREE.InstancedMesh(geometry, material, data.voxels.length);
    model.instanceMatrix.setUsage(THREE.StaticDrawUsage);
    const transform = new THREE.Object3D();
    const color = new THREE.Color();
    data.voxels.forEach((voxel, index) => {
      const [x, y, z, size, red, green, blue] = voxel;
      transform.position.set(x, z, y);
      transform.scale.setScalar(Math.max(0.000_001, size));
      transform.updateMatrix();
      model.setMatrixAt(index, transform.matrix);
      color.setRGB(red / 255, green / 255, blue / 255, THREE.SRGBColorSpace);
      model.setColorAt(index, color);
    });
    model.instanceMatrix.needsUpdate = true;
    if (model.instanceColor) model.instanceColor.needsUpdate = true;
    model.computeBoundingSphere();
    engine.scene.add(model);
    engine.model = model;

    const minimum = data.bounds.min;
    const maximum = data.bounds.max;
    const box = new THREE.Box3(
      new THREE.Vector3(minimum[0], minimum[2], minimum[1]),
      new THREE.Vector3(maximum[0], maximum[2], maximum[1]),
    );
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

    const resetView = () => {
      const distance = Math.max(diameter * 1.35, 0.5);
      engine.camera.near = Math.max(distance / 2_000, 0.000_1);
      engine.camera.far = Math.max(distance * 50, 100);
      engine.camera.position.set(
        center.x + distance * 0.82,
        center.y + distance * 0.68,
        center.z + distance * 0.9,
      );
      engine.camera.updateProjectionMatrix();
      engine.controls.target.copy(center);
      engine.controls.minDistance = Math.max(diameter * 0.08, 0.02);
      engine.controls.maxDistance = Math.max(diameter * 30, 20);
      engine.controls.update();
    };
    engine.resetView = resetView;
    resetView();
  }, [data]);

  return (
    <div className="voxel-viewer" aria-busy={loading}>
      <div ref={mountRef} className="voxel-canvas" />
      {data && !loading && <span className="voxel-count">{data.voxel_count.toLocaleString()} 体素</span>}
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
  engine.resetView = null;
}
