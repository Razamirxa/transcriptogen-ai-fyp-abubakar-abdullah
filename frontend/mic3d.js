/* Real 3D retro chrome microphone (Three.js). Rotates towards the cursor over the hero,
   can be dragged, idles with a slow turn, and pulses indigo "sound rings". Theme-aware. */
import * as THREE from "three";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";

const host = document.getElementById("heroArt");
const stage = document.querySelector(".stage");
if (host && stage && window.WebGLRenderingContext) {
  host.innerHTML = "";
  host.classList.add("webgl");
  const W = () => host.clientWidth || 360, H = () => host.clientHeight || 430;

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.setSize(W(), H());
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  host.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;

  const camera = new THREE.PerspectiveCamera(28, W() / H(), 0.1, 50);
  camera.position.set(0, 1.0, 8.6);
  camera.lookAt(0, 0.45, 0);

  // ---- materials ----
  const chrome = new THREE.MeshStandardMaterial({ color: 0xE9E9F2, metalness: 1.0, roughness: 0.18 });
  const chromeSoft = new THREE.MeshStandardMaterial({ color: 0xC9C9D6, metalness: 0.95, roughness: 0.32 });
  const dark = new THREE.MeshStandardMaterial({ color: 0x14141C, metalness: 0.4, roughness: 0.6 });
  const accent = () => getComputedStyle(document.documentElement).getPropertyValue("--accent").trim() || "#4F46E5";

  // ---- microphone ----
  const mic = new THREE.Group();
  const head = new THREE.Group(); head.position.y = 1.55;
  head.add(new THREE.Mesh(new THREE.CapsuleGeometry(0.50, 0.62, 12, 32), dark));               // inner dark body
  // vertical chrome grille bars around the head
  const barGeo = new THREE.BoxGeometry(0.075, 1.46, 0.075);
  for (let i = 0; i < 18; i++) {
    const a = (i / 18) * Math.PI * 2;
    const bar = new THREE.Mesh(barGeo, chrome);
    bar.position.set(Math.sin(a) * 0.565, 0.0, Math.cos(a) * 0.565);
    bar.rotation.y = a;
    head.add(bar);
  }
  // rings (top, bottom, middle band) + cap
  const ring = (y, r, t, m = chrome) => { const q = new THREE.Mesh(new THREE.TorusGeometry(r, t, 18, 64), m); q.rotation.x = Math.PI / 2; q.position.y = y; head.add(q); };
  ring(0.62, 0.50, 0.075); ring(-0.62, 0.50, 0.075); ring(0.0, 0.60, 0.045, chromeSoft);
  const cap = new THREE.Mesh(new THREE.SphereGeometry(0.34, 32, 16, 0, Math.PI * 2, 0, Math.PI / 2), chrome); cap.position.y = 0.78; head.add(cap);
  const capBase = new THREE.Mesh(new THREE.CylinderGeometry(0.34, 0.36, 0.08, 40), chrome); capBase.position.y = 0.74; head.add(capBase);
  const capBaseBottom = new THREE.Mesh(new THREE.CylinderGeometry(0.30, 0.22, 0.26, 40), chrome); capBaseBottom.position.y = -0.85; head.add(capBaseBottom);
  // badge
  const badge = new THREE.Mesh(new THREE.CylinderGeometry(0.13, 0.13, 0.03, 32), new THREE.MeshStandardMaterial({ color: 0x4F46E5, metalness: 0.6, roughness: 0.35 }));
  badge.rotation.x = Math.PI / 2; badge.position.set(0, -0.1, 0.62); head.add(badge);
  mic.add(head);
  // yoke + neck
  const yoke = new THREE.Mesh(new THREE.TorusGeometry(0.62, 0.05, 14, 48, Math.PI), chrome); yoke.rotation.z = Math.PI; yoke.position.y = 1.55; mic.add(yoke);
  const pivotL = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.09, 0.12, 24), chrome); pivotL.rotation.z = Math.PI / 2; pivotL.position.set(-0.66, 1.55, 0); mic.add(pivotL);
  const pivotR = pivotL.clone(); pivotR.position.x = 0.66; mic.add(pivotR);
  const neck = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.16, 0.55, 32), chrome); neck.position.y = 0.66; mic.add(neck);
  const collar = new THREE.Mesh(new THREE.CylinderGeometry(0.2, 0.2, 0.1, 32), chromeSoft); collar.position.y = 0.36; mic.add(collar);
  // stand + base
  const stand = new THREE.Mesh(new THREE.CylinderGeometry(0.11, 0.13, 1.2, 32), chrome); stand.position.y = -0.25; mic.add(stand);
  const base = new THREE.Mesh(new THREE.CylinderGeometry(0.55, 0.75, 0.16, 48), chrome); base.position.y = -0.92; mic.add(base);
  const baseRim = new THREE.Mesh(new THREE.TorusGeometry(0.72, 0.05, 16, 64), chromeSoft); baseRim.rotation.x = Math.PI / 2; baseRim.position.y = -0.86; mic.add(baseRim);
  const baseTop = new THREE.Mesh(new THREE.CylinderGeometry(0.28, 0.4, 0.14, 40), chrome); baseTop.position.y = -0.78; mic.add(baseTop);
  mic.position.y = -0.15;
  scene.add(mic);

  // ---- pulsing sound rings ----
  const rings = [];
  for (let i = 0; i < 3; i++) {
    const m = new THREE.MeshBasicMaterial({ color: new THREE.Color(accent()), transparent: true, opacity: 0.35, side: THREE.DoubleSide });
    const r = new THREE.Mesh(new THREE.TorusGeometry(0.9, 0.028, 12, 96), m);
    r.rotation.x = Math.PI / 2; r.position.y = 1.4; r.userData.phase = i / 3; rings.push(r); scene.add(r);
  }

  // ---- lights (tweaked per theme) ----
  const key = new THREE.DirectionalLight(0xffffff, 1.4); key.position.set(3, 5, 4); scene.add(key);
  const rim = new THREE.DirectionalLight(0x8B85FF, 1.2); rim.position.set(-4, 2, -3); scene.add(rim);
  const amb = new THREE.AmbientLight(0xffffff, 0.35); scene.add(amb);
  const applyTheme = () => { const darkMode = document.documentElement.dataset.theme === "dark"; renderer.toneMappingExposure = darkMode ? 0.85 : 1.05; amb.intensity = darkMode ? 0.18 : 0.35; rim.intensity = darkMode ? 1.8 : 1.2; rings.forEach((r) => r.material.color.set(accent())); };
  applyTheme(); new MutationObserver(applyTheme).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

  // ---- interaction: cursor over the hero rotates the mic in full 3D; drag to spin; idle turn ----
  const target = { x: 0, y: 0 }; let hovering = false, dragging = false, lastX = 0, spin = 0;
  const onMove = (e) => { const r = stage.getBoundingClientRect(); const nx = ((e.clientX - r.left) / r.width - 0.5) * 2, ny = ((e.clientY - r.top) / r.height - 0.5) * 2;
    if (dragging) { spin += (e.clientX - lastX) * 0.012; lastX = e.clientX; } target.y = nx * 1.1; target.x = ny * 0.45; hovering = true; };
  stage.addEventListener("pointermove", onMove);
  stage.addEventListener("pointerleave", () => { hovering = false; dragging = false; target.x = 0; target.y = 0; });
  host.addEventListener("pointerdown", (e) => { dragging = true; lastX = e.clientX; host.setPointerCapture(e.pointerId); });
  host.addEventListener("pointerup", () => { dragging = false; });
  host.style.cursor = "grab";

  const clock = new THREE.Clock();
  const tick = () => {
    const t = clock.getElapsedTime();
    if (!hovering) spin += 0.004;
    mic.rotation.y += ((target.y + spin) - mic.rotation.y) * 0.08;
    mic.rotation.x += (target.x * 0.6 - mic.rotation.x) * 0.08;
    mic.position.y = -0.15 + Math.sin(t * 0.9) * 0.05;
    rings.forEach((r) => { const p = ((t * 0.45) + r.userData.phase) % 1; const s = 0.7 + p * 1.1; r.scale.set(s, s, s); r.material.opacity = 0.42 * (1 - p); r.position.y = 1.4 + p * 0.25; });
    renderer.render(scene, camera);
    requestAnimationFrame(tick);
  };
  tick();
  new ResizeObserver(() => { renderer.setSize(W(), H()); camera.aspect = W() / H(); camera.updateProjectionMatrix(); }).observe(host);
}
