import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three/webgpu';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

type XYZ = [number, number, number];
export type HumanView = { scene_id: string; release_id: string; truth_version_id: string;
  frame_id: string; view_version_id: string; package_sha256: string; bounds: [XYZ, XYZ];
  objects: { object_id: string; type_id: string; properties: { name: string }; anchor_xyz: XYZ }[];
  cells: { bounds: [XYZ, XYZ]; state: string; reason: string; evidence_ids: string[] }[] };
const colors: Record<string, number> = { occupied: 0xc65e50, observed_free: 0x3ca784, unknown: 0xc8a257 };

export default function SpatialView({ data, point }: { data: HumanView; point: number[] | null }) {
  const host = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState('正在初始化渲染器…');
  useEffect(() => {
    const element = host.current!;
    let cancelled = false, initialized = false;
    let renderer: THREE.WebGPURenderer | undefined;
    let controls: OrbitControls | undefined;
    let observer: ResizeObserver | undefined;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color('#edf2f4');
    const camera = new THREE.PerspectiveCamera(42, 1, 0.01, 500);
    camera.up.set(0, 0, 1);
    const min = new THREE.Vector3(...data.bounds[0]), max = new THREE.Vector3(...data.bounds[1]);
    const center = min.clone().add(max).multiplyScalar(.5), extent = max.clone().sub(min).length();
    camera.position.copy(center).add(new THREE.Vector3(extent * .72, -extent * .83, extent * .68));
    camera.lookAt(center);
    function box(bounds: [XYZ, XYZ], color: number, opacity: number, wire = false) {
      const a = new THREE.Vector3(...bounds[0]), b = new THREE.Vector3(...bounds[1]), size = b.clone().sub(a);
      const geometry = new THREE.BoxGeometry(size.x, size.y, size.z);
      const mesh = wire ? new THREE.LineSegments(new THREE.EdgesGeometry(geometry),
        new THREE.LineBasicMaterial({ color, transparent: true, opacity })) : new THREE.Mesh(geometry,
        new THREE.MeshBasicMaterial({ color, transparent: true, opacity, depthWrite: false }));
      if (wire) geometry.dispose();
      mesh.position.copy(a.add(b).multiplyScalar(.5)); scene.add(mesh);
    }
    for (const cell of data.cells) box(cell.bounds, colors[cell.state] ?? colors.unknown,
      cell.state === 'unknown' ? .09 : cell.state === 'occupied' ? .65 : .22);
    for (const cell of data.cells.filter(c => c.reason === 'conflict')) box(cell.bounds, 0x974caa, 1, true);
    box(data.bounds, 0x607d89, .7, true);
    for (const object of data.objects) {
      const marker = new THREE.Mesh(new THREE.SphereGeometry(.12), new THREE.MeshBasicMaterial({ color: 0x164e65 }));
      marker.position.set(...object.anchor_xyz); scene.add(marker);
    }
    if (point) {
      const marker = new THREE.Mesh(new THREE.SphereGeometry(.18), new THREE.MeshBasicMaterial({ color: 0x2875ec }));
      marker.position.set(point[0], point[1], point[2]); scene.add(marker);
    }
    async function start() {
      try {
        setStatus('正在初始化渲染器…');
        renderer = new THREE.WebGPURenderer({ antialias: true });
        await renderer.init();
        initialized = true;
        if (cancelled) { renderer.dispose(); return; }
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        renderer.domElement.setAttribute('aria-label', '合成空间三维视图，Z轴向上，拖动旋转，滚轮缩放');
        element.appendChild(renderer.domElement);
        controls = new OrbitControls(camera, renderer.domElement); controls.target.copy(center); controls.update();
        observer = new ResizeObserver(() => {
          renderer!.setSize(element.clientWidth, element.clientHeight);
          camera.aspect = element.clientWidth / element.clientHeight; camera.updateProjectionMatrix();
        });
        observer.observe(element);
        renderer.setAnimationLoop(() => { if (!cancelled) renderer!.render(scene, camera); });
        const backend = renderer.backend as unknown as { isWebGPUBackend?: boolean };
        setStatus(backend.isWebGPUBackend ? 'WebGPU' : 'WebGL2（兼容回退）');
      } catch (error) {
        if (!cancelled) setStatus(`三维渲染不可用：${error instanceof Error ? error.message : '初始化失败'}；可核对下方数据`);
      }
    }
    void start();
    return () => {
      cancelled = true; observer?.disconnect(); controls?.dispose();
      if (initialized) { renderer?.setAnimationLoop(null); renderer?.dispose(); }
      renderer?.domElement.remove();
      scene.traverse(object => {
        if (object instanceof THREE.Mesh || object instanceof THREE.LineSegments) {
          object.geometry.dispose();
          (Array.isArray(object.material) ? object.material : [object.material]).forEach(material => material.dispose());
        }
      });
    };
  }, [data, point]);
  return <><div className="view-meta"><span>{data.view_version_id}</span><strong role="status">{status}</strong></div>
    <div className="spatial-canvas" ref={host} />
    <div className="legend"><span>🟥 占据</span><span>🟩 已观测空闲</span><span>🟨 未知</span><span>🟪 冲突（未知）</span><span>🔵 查询点</span></div>
    <p>拖动旋转 · 滚轮缩放 · Z轴向上 · 单位米。半透明体表示合成状态分区；对象仅有锚点。渲染失败不表示空间未知。</p>
    <table className="objects"><thead><tr><th>对象 / 类型</th><th>锚点 XYZ（米）</th></tr></thead><tbody>{data.objects.map(object =>
      <tr key={object.object_id}><td>{object.properties.name}<small>{object.object_id} · {object.type_id}</small></td><td>[{object.anchor_xyz.join(', ')}]</td></tr>)}</tbody></table>
    <details><summary>空间状态分区明细（{data.cells.length}块）</summary><ul>{data.cells.map((cell, index) =>
      <li key={index}>[{cell.bounds[0].join(', ')}] → [{cell.bounds[1].join(', ')}]：{cell.state} / {cell.reason}；证据 {cell.evidence_ids.join(', ') || '无'}</li>)}</ul></details>
  </>;
}
