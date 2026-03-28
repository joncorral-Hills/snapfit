/**
 * camera.js — SnapFit 5-phase scan wizard
 *
 * Phase 1 — Live camera   (#phase-live)
 * Phase 2 — Analysis      (#phase-analysis)  POST /api/analyze-contour
 * Phase 3 — Dot editor    (#phase-edit)       SVG draggable polygon
 * Phase 4 — Scale input   (#phase-scale)
 * Phase 5 — 3D Preview   (#phase-preview)    Three.js STL viewer + save
 */

/* ── DOM refs ─────────────────────────────────────────────────────────────── */
const scanModal    = document.getElementById('scan-modal');
const scanBackdrop = document.getElementById('scan-backdrop');
const scanBtn      = document.getElementById('scan-btn');
const scanClose    = document.getElementById('scan-close');
const overlayMsg   = document.getElementById('scan-overlay-msg');

// Phase containers
const phaseLive     = document.getElementById('phase-live');
const phaseAnalysis = document.getElementById('phase-analysis');
const phaseEdit     = document.getElementById('phase-edit');
const phaseScale    = document.getElementById('phase-scale');
const phasePreview  = document.getElementById('phase-preview');

// Phase-1 elements
const scanVideo    = document.getElementById('scan-video');
const analyzeBtn   = document.getElementById('analyze-btn');

// Phase-2 elements
const captureCanvas    = document.getElementById('scan-capture');
const analysisMsg      = document.getElementById('scan-analysis-msg');

// Phase-3 elements
const frozenCanvas     = document.getElementById('scan-frozen');
const dotSvg           = document.getElementById('dot-svg');
const scanWarning      = document.getElementById('scan-warning');
const resetPtsBtn      = document.getElementById('reset-pts-btn');
const addPtBtn         = document.getElementById('add-pt-btn');
const removePtBtn      = document.getElementById('remove-pt-btn');
const confirmShapeBtn  = document.getElementById('confirm-shape-btn');
const editHint         = document.getElementById('edit-hint');

// Phase-4 elements
const dimWidth      = document.getElementById('dim-width');
const dimHeight     = document.getElementById('dim-height');
const dimDepth      = document.getElementById('dim-depth');
const dimUnitLabels = document.querySelectorAll('#phase-scale .dim-unit');
const unitOptBtns   = document.querySelectorAll('#unit-toggle .unit-opt');
const useDimsBtn    = document.getElementById('use-dims-btn');
const backToEditBtn = document.getElementById('back-to-edit-btn');

// Phase-5 elements
const stlValidBadge  = document.getElementById('stl-valid-badge');
const stlLoading     = document.getElementById('stl-loading');
const stlCanvas      = document.getElementById('stl-canvas');
const backToScaleBtn = document.getElementById('back-to-scale-btn');
const downloadStlBtn = document.getElementById('download-stl-btn');
const saveToolBtn    = document.getElementById('save-tool-btn');
const saveBrandEl    = document.getElementById('save-brand');
const saveModelEl    = document.getElementById('save-model');
const saveStatusEl   = document.getElementById('save-status');

// Step indicator dots
const stepEls = document.querySelectorAll('.scan-step');

/* ── State ────────────────────────────────────────────────────────────────── */
let mediaStream      = null;
let lastB64          = null;   // base64 of captured frame
let autoPoints       = [];     // original detected points [{x,y} in 0-1 pct space]
let currentPoints    = [];     // working copy (user may drag)
let bboxPct          = null;   // {x,y,w,h} in 0-1 fractions
let addPointMode     = false;
let removePointMode  = false;
let currentUnit      = 'mm';
let lastFilename     = null;   // most recently generated STL filename
let lastDims         = null;   // {w, h, d} in mm at time of generation
let stlThreeRenderer = null;   // Three.js WebGL renderer (kept for disposal)

const MM_PER_IN = 25.4;
function toDisplay(mm)   { return currentUnit === 'in' ? +(mm  / MM_PER_IN).toFixed(3) : +mm.toFixed(1); }
function toMm(display)   { return currentUnit === 'in' ? display * MM_PER_IN : display; }

/* ── Helpers: show / hide (CSS-override-proof) ───────────────────────────── */
function hide(el) { if (el) { el.hidden = true;  el.style.display = 'none'; } }
function show(el, d = '') { if (el) { el.hidden = false; el.style.display = d; } }

function setStep(n) {
  stepEls.forEach(el => el.classList.toggle('active', +el.dataset.step === n));
}

function showPhase(phase) {
  [phaseLive, phaseAnalysis, phaseEdit, phaseScale, phasePreview].forEach(hide);
  show(phase);
}

/* ── Overlay helpers ─────────────────────────────────────────────────────── */
function showOverlay(msg) { overlayMsg.textContent = msg; show(overlayMsg); }
function hideOverlay()     { hide(overlayMsg); }

/* ── Camera ──────────────────────────────────────────────────────────────── */
async function startCamera() {
  showOverlay('Starting camera…');
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 960 } },
      audio: false,
    });
    scanVideo.srcObject = mediaStream;
    await scanVideo.play();
    hideOverlay();
  } catch (err) {
    showOverlay(
      err.name === 'NotAllowedError'
        ? '📷 Camera access denied. Allow camera access and try again.'
        : `📷 Could not open camera: ${err.message}`
    );
    hide(analyzeBtn);
  }
}

function stopCamera() {
  if (mediaStream) {
    mediaStream.getTracks().forEach(t => t.stop());
    mediaStream = null;
  }
  scanVideo.srcObject = null;
}

/* ── Open / close modal ──────────────────────────────────────────────────── */
function openModal() {
  scanModal.hidden        = false;
  scanModal.style.display = 'flex';
  scanBackdrop.hidden        = false;
  scanBackdrop.style.display = 'block';
  document.body.style.overflow = 'hidden';
  enterLivePhase();
}

function closeModal() {
  stopCamera();
  scanModal.hidden        = true;
  scanModal.style.display = 'none';
  scanBackdrop.hidden        = true;
  scanBackdrop.style.display = 'none';
  document.body.style.overflow = '';
}

/* ── Phase 1: Live ───────────────────────────────────────────────────────── */
function enterLivePhase() {
  showPhase(phaseLive);
  setStep(1);
  lastB64 = null;
  autoPoints = [];
  currentPoints = [];
  addPointMode = false;
  removePointMode = false;
  clearDotSvg();
  startCamera();
}

/* ── Phase 2: Analysis ───────────────────────────────────────────────────── */
async function enterAnalysisPhase() {
  // Freeze frame from video using native resolution
  const w = scanVideo.videoWidth  || 640;
  const h = scanVideo.videoHeight || 480;
  captureCanvas.width  = w;
  captureCanvas.height = h;
  captureCanvas.getContext('2d').drawImage(scanVideo, 0, 0, w, h);

  // Downscale for API POST (max 640px wide)
  const small = downscale(captureCanvas, 640);
  lastB64 = small.toDataURL('image/jpeg', 0.85);

  stopCamera();
  showPhase(phaseAnalysis);
  setStep(2);

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 30_000);

  try {
    const res = await fetch('/api/analyze-contour', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
      body: JSON.stringify({ image: lastB64, target_pts: 12 }),
    });
    clearTimeout(timer);
    if (!res.ok) {
      const e = await res.json().catch(() => ({}));
      throw new Error(e.detail || `HTTP ${res.status}`);
    }
    const data = await res.json();
    autoPoints    = data.points.map(([x, y]) => ({ x, y }));
    bboxPct       = data.bounding_box_pct;
    currentPoints = autoPoints.map(p => ({ ...p }));

    enterEditPhase(data.warning);
  } catch (err) {
    clearTimeout(timer);
    const msg = err.name === 'AbortError'
      ? 'Analysis timed out — try again against a plain background.'
      : `Analysis failed: ${err.message}`;
    // Go back to live with error
    enterLivePhase();
    showOverlay(`⚠️ ${msg}`);
  }
}

function downscale(src, maxW) {
  const ratio = Math.min(1, maxW / src.width);
  const w = Math.round(src.width * ratio);
  const h = Math.round(src.height * ratio);
  const tmp = document.createElement('canvas');
  tmp.width = w; tmp.height = h;
  tmp.getContext('2d').drawImage(src, 0, 0, w, h);
  return tmp;
}

/* ── Phase 3: SVG Dot Editor ─────────────────────────────────────────────── */
function enterEditPhase(warning = null) {
  showPhase(phaseEdit);
  setStep(3);
  // Reset edit modes whenever we enter (re-)edit
  setAddPointMode(false);
  setRemovePointMode(false);

  // Draw frozen frame into #scan-frozen (sized to display container)
  const viewport = document.getElementById('scan-viewport-edit');
  setTimeout(() => {
    const dw = viewport.clientWidth  || 480;
    const dh = Math.round(dw * (captureCanvas.height / captureCanvas.width));
    frozenCanvas.width  = dw;
    frozenCanvas.height = dh;
    frozenCanvas.getContext('2d').drawImage(captureCanvas, 0, 0, dw, dh);
    renderDotOverlay(dw, dh);
  }, 50);  // small delay to let layout settle

  if (warning) {
    scanWarning.textContent = `⚠️ ${warning}`;
    show(scanWarning);
  } else {
    hide(scanWarning);
  }
}

function renderDotOverlay(w, h) {
  clearDotSvg();
  dotSvg.setAttribute('viewBox', `0 0 ${w} ${h}`);
  dotSvg.setAttribute('width', w);
  dotSvg.setAttribute('height', h);

  const ns = 'http://www.w3.org/2000/svg';

  // Closed polyline
  const poly = document.createElementNS(ns, 'polygon');
  poly.id = 'dot-polygon';
  poly.setAttribute('fill', 'rgba(245,158,11,0.15)');
  poly.setAttribute('stroke', '#f59e0b');
  poly.setAttribute('stroke-width', '2');
  poly.setAttribute('stroke-linejoin', 'round');
  dotSvg.appendChild(poly);

  updatePolygon(w, h);

  // Draggable circles — colour/cursor depends on current mode
  currentPoints.forEach((pt, i) => {
    const cx = pt.x * w;
    const cy = pt.y * h;
    const circle = document.createElementNS(ns, 'circle');
    circle.setAttribute('cx', cx);
    circle.setAttribute('cy', cy);
    circle.setAttribute('r', 9);
    circle.setAttribute('fill',         removePointMode ? '#ef4444' : '#f59e0b');
    circle.setAttribute('stroke',       '#0e0f11');
    circle.setAttribute('stroke-width', 2);
    circle.setAttribute('cursor',       removePointMode ? 'no-drop' : 'grab');
    circle.dataset.idx = i;
    makeDraggable(circle, w, h);
    dotSvg.appendChild(circle);
  });
}

function updatePolygon(w, h) {
  const poly = document.getElementById('dot-polygon');
  if (!poly) return;
  const pts = currentPoints.map(p => `${(p.x * w).toFixed(1)},${(p.y * h).toFixed(1)}`).join(' ');
  poly.setAttribute('points', pts);
}

function clearDotSvg() {
  while (dotSvg.firstChild) dotSvg.removeChild(dotSvg.firstChild);
}

function makeDraggable(circle, svgW, svgH) {
  let dragging = false;
  const idx = +circle.dataset.idx;

  circle.addEventListener('pointerdown', e => {
    // Remove mode: delete this dot (min 3 points)
    if (removePointMode) {
      if (currentPoints.length <= 3) return; // enforce minimum
      currentPoints.splice(idx, 1);
      renderDotOverlay(svgW, svgH);
      return;
    }
    e.preventDefault();
    dragging = true;
    circle.setPointerCapture(e.pointerId);
    circle.setAttribute('cursor', 'grabbing');
  });

  circle.addEventListener('pointermove', e => {
    if (!dragging) return;
    const rect = dotSvg.getBoundingClientRect();
    const x = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const y = Math.max(0, Math.min(1, (e.clientY - rect.top)  / rect.height));
    currentPoints[idx] = { x, y };
    circle.setAttribute('cx', x * svgW);
    circle.setAttribute('cy', y * svgH);
    updatePolygon(svgW, svgH);
  });

  circle.addEventListener('pointerup', () => {
    dragging = false;
    circle.setAttribute('cursor', removePointMode ? 'no-drop' : 'grab');
  });
}

/* ── Phase 4: Scale ──────────────────────────────────────────────────────── */
function setUnit(unit) {
  if (unit === currentUnit) return;
  const factor = unit === 'in' ? 1 / MM_PER_IN : MM_PER_IN;
  [dimWidth, dimHeight, dimDepth].forEach(inp => {
    if (inp.value) inp.value = +(parseFloat(inp.value) * factor).toFixed(unit === 'in' ? 3 : 1);
  });
  currentUnit = unit;
  // Update labels
  dimUnitLabels.forEach(el => el.textContent = unit);
  // Update step/min/max
  const isIn = unit === 'in';
  dimWidth.step  = isIn ? '0.01'  : '0.5';  dimWidth.min  = isIn ? '0.4'   : '10';  dimWidth.max  = isIn ? '24'  : '600';
  dimHeight.step = isIn ? '0.01'  : '0.5';  dimHeight.min = isIn ? '0.4'   : '10';  dimHeight.max = isIn ? '40'  : '1000';
  dimDepth.step  = isIn ? '0.01'  : '0.5';  dimDepth.min  = isIn ? '0.4'   : '10';  dimDepth.max  = isIn ? '16'  : '400';
  // Update toggle button active state
  unitOptBtns.forEach(b => b.classList.toggle('active', b.dataset.unit === unit));
}

function enterScalePhase() {
  showPhase(phaseScale);
  setStep(4);
  // Always reset to mm when entering so values are consistent
  setUnit('mm');

  // Pre-fill W/H from bounding box percentages
  if (bboxPct) {
    const ASSUME_HEIGHT_MM = 200;
    const pxPerMm = bboxPct.h / ASSUME_HEIGHT_MM;
    dimHeight.value = Math.round(ASSUME_HEIGHT_MM);
    dimWidth.value  = Math.round(bboxPct.w / pxPerMm);
  }
  if (!dimDepth.value) dimDepth.value = 80;
}

/* ── Use Dimensions → generate STL → Phase 5 ─────────────────────────────── */
async function useDimensions() {
  const w = toMm(parseFloat(dimWidth.value)  || toDisplay(150));
  const h = toMm(parseFloat(dimHeight.value) || toDisplay(200));
  const d = toMm(parseFloat(dimDepth.value)  || toDisplay(80));
  const mountingRadio = document.querySelector('input[name="scan_mounting"]:checked');
  const mountingSystem = mountingRadio ? mountingRadio.value : 'blank';

  useDimsBtn.disabled = true;
  useDimsBtn.textContent = 'Generating…';

  let contourPayload = null;
  if (currentPoints && currentPoints.length >= 3) {
    contourPayload = currentPoints.map(p => [
      +(p.x * w).toFixed(2),
      +(p.y * h).toFixed(2),
    ]);
  }

  try {
    const genRes = await fetch('/api/generate-from-dims', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        width_mm: w, height_mm: h, depth_mm: d,
        mounting_system: mountingSystem,
        label: 'scanned_tool',
        ...(contourPayload ? { contour_points: contourPayload, px_per_mm: 1.0 } : {}),
      }),
    });
    if (!genRes.ok) throw new Error(`Generate failed: ${genRes.status}`);
    const data = await genRes.json();
    lastFilename = data.filename;
    lastDims = { w, h, d };
    enterPreviewPhase(data.filename, data.validation);
  } catch (err) {
    alert(`⚠️ ${err.message}`);
  } finally {
    useDimsBtn.disabled = false;
    useDimsBtn.textContent = 'Generate STL ↓';
  }
}

/* ── Phase 5 — 3D preview ─────────────────────────────────────────────────── */
function enterPreviewPhase(filename, validation) {
  showPhase(phasePreview);
  setStep(5);
  saveStatusEl.textContent = '';
  saveBrandEl.value = '';
  saveModelEl.value = '';
  showValidationBadge(validation);
  loadSTLPreview(filename);
}

function showValidationBadge(v) {
  if (!v) { hide(stlValidBadge); return; }
  stlValidBadge.hidden = false;
  stlValidBadge.style.display = '';
  if (v.is_valid) {
    stlValidBadge.textContent = `✅ ${v.triangle_count.toLocaleString()} triangles — mesh OK`;
    stlValidBadge.className = 'stl-valid-badge stl-valid-ok';
  } else {
    stlValidBadge.textContent = `⚠️ ${v.warning || 'Mesh may have issues'}`;
    stlValidBadge.className = 'stl-valid-badge stl-valid-warn';
  }
}

function loadSTLPreview(filename) {
  // Dispose old renderer if any
  if (stlThreeRenderer) { stlThreeRenderer.dispose(); stlThreeRenderer = null; }
  stlCanvas.style.display = 'none';
  show(stlLoading);

  const viewport = document.getElementById('stl-viewport');
  const W = viewport.clientWidth || 400;
  const H = viewport.clientHeight || 280;

  const scene    = new THREE.Scene();
  scene.background = new THREE.Color(0x0d0d12);
  const camera3  = new THREE.PerspectiveCamera(45, W / H, 0.1, 2000);
  const renderer = new THREE.WebGLRenderer({ canvas: stlCanvas, antialias: true });
  stlThreeRenderer = renderer;
  renderer.setSize(W, H);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

  scene.add(new THREE.AmbientLight(0xffffff, 0.6));
  const dir = new THREE.DirectionalLight(0xffffff, 0.9);
  dir.position.set(1, 2, 3);
  scene.add(dir);
  scene.add(new THREE.DirectionalLight(0x8888ff, 0.3).position.set(-1, -1, -1) && dir);

  const controls = new THREE.OrbitControls(camera3, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;

  const loader = new THREE.STLLoader();
  loader.load(
    `/api/download/${encodeURIComponent(filename)}`,
    (geometry) => {
      geometry.computeVertexNormals();
      const mat  = new THREE.MeshStandardMaterial({ color: 0xf97316, roughness: 0.6, metalness: 0.1 });
      const mesh = new THREE.Mesh(geometry, mat);
      geometry.center();
      geometry.computeBoundingSphere();
      const r = geometry.boundingSphere.radius;
      camera3.position.set(0, r * 0.4, r * 2.5);
      camera3.lookAt(0, 0, 0);
      controls.target.set(0, 0, 0);
      scene.add(mesh);
      hide(stlLoading);
      stlCanvas.style.display = 'block';

      let animId;
      function animate() {
        animId = requestAnimationFrame(animate);
        controls.update();
        renderer.render(scene, camera3);
      }
      animate();
      // Stop animation when phase leaves view
      phasePreview._stopAnim = () => cancelAnimationFrame(animId);
    },
    undefined,
    (err) => { stlLoading.textContent = '⚠️ Preview failed — download below still works.'; }
  );
}

async function triggerDownload() {
  if (!lastFilename) return;
  const dlRes = await fetch(`/api/download/${encodeURIComponent(lastFilename)}`);
  if (!dlRes.ok) { alert('Download failed'); return; }
  const blob = await dlRes.blob();
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href = url; a.download = lastFilename;
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
}

async function saveToolToCatalog() {
  const brand = saveBrandEl.value.trim();
  const model = saveModelEl.value.trim();
  if (!brand || !model) { saveStatusEl.textContent = '⚠️ Enter brand and model name.'; return; }
  saveToolBtn.disabled = true;
  saveStatusEl.textContent = 'Saving…';
  try {
    const res = await fetch('/api/save-scanned-tool', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        brand, model_name: model,
        width_mm: lastDims?.w || 150,
        height_mm: lastDims?.h || 200,
        depth_mm:  lastDims?.d || 80,
      }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    saveStatusEl.style.color = 'var(--amber)';
    saveStatusEl.textContent = `✅ Saved as "${data.tool.brand} ${data.tool.model_name}" (ID ${data.tool_id})`;
    saveToolBtn.textContent = 'Saved ✓';
  } catch (err) {
    saveStatusEl.textContent = `❌ ${err.message}`;
    saveToolBtn.disabled = false;
  }
}

/* ── Event Listeners ─────────────────────────────────────────────────────── */
scanBtn.addEventListener('click', openModal);
scanClose.addEventListener('click', closeModal);
scanBackdrop.addEventListener('click', closeModal);

analyzeBtn.addEventListener('click', enterAnalysisPhase);
resetPtsBtn.addEventListener('click', () => {
  currentPoints = autoPoints.map(p => ({ ...p }));
  renderDotOverlay(frozenCanvas.width, frozenCanvas.height);
});
confirmShapeBtn.addEventListener('click', enterScalePhase);

/* ── Add Point mode ─────────────────────────────────────────────────────── */
function setAddPointMode(active) {
  addPointMode = active;
  if (active) setRemovePointMode(false); // mutual exclusion
  addPtBtn.style.color   = active ? 'var(--amber)' : '';
  addPtBtn.style.outline = active ? '2px solid var(--amber)' : '';
  if (!removePointMode) {
    editHint.innerHTML = active
      ? '🎯 <strong>Click anywhere</strong> on the image to place a new dot'
      : 'Drag dots to adjust · click <strong>+ Point</strong> or <strong>− Point</strong> to edit';
  }
  dotSvg.style.cursor = active ? 'cell' : 'crosshair';
}

function setRemovePointMode(active) {
  removePointMode = active;
  if (active) setAddPointMode(false); // mutual exclusion
  removePtBtn.style.color   = active ? '#ef4444' : '';
  removePtBtn.style.outline = active ? '2px solid #ef4444' : '';
  // Re-render dots so their cursor/colour reflects the mode
  renderDotOverlay(frozenCanvas.width, frozenCanvas.height);
  editHint.innerHTML = active
    ? '🗑️ <strong>Click a dot</strong> to remove it (minimum 3 remain)'
    : 'Drag dots to adjust · click <strong>+ Point</strong> or <strong>− Point</strong> to edit';
  if (active) dotSvg.style.cursor = 'default';
}

addPtBtn.addEventListener('click', () => setAddPointMode(!addPointMode));
removePtBtn.addEventListener('click', () => setRemovePointMode(!removePointMode));

/** Find the index i such that inserting after currentPoints[i] minimises
 *  the perpendicular distance from (px,py) to the segment [i → i+1 mod n]. */
function nearestEdgeIndex(px, py) {
  const n = currentPoints.length;
  let bestIdx = 0, bestDist = Infinity;
  for (let i = 0; i < n; i++) {
    const a = currentPoints[i];
    const b = currentPoints[(i + 1) % n];
    const dx = b.x - a.x, dy = b.y - a.y;
    const lenSq = dx * dx + dy * dy;
    let t = lenSq > 0 ? ((px - a.x) * dx + (py - a.y) * dy) / lenSq : 0;
    t = Math.max(0, Math.min(1, t));
    const qx = a.x + t * dx, qy = a.y + t * dy;
    const dist = Math.hypot(px - qx, py - qy);
    if (dist < bestDist) { bestDist = dist; bestIdx = i; }
  }
  return bestIdx;
}

dotSvg.addEventListener('click', e => {
  if (!addPointMode) return;
  const rect = dotSvg.getBoundingClientRect();
  const px = (e.clientX - rect.left) / rect.width;
  const py = (e.clientY - rect.top)  / rect.height;
  const insertAfter = nearestEdgeIndex(px, py);
  currentPoints.splice(insertAfter + 1, 0, { x: px, y: py });
  renderDotOverlay(frozenCanvas.width, frozenCanvas.height);
  // Stay in add-point mode so user can add multiple points in a row
});
backToEditBtn.addEventListener('click', () => {
  showPhase(phaseEdit);
  setStep(3);
});
unitOptBtns.forEach(b => b.addEventListener('click', () => setUnit(b.dataset.unit)));
useDimsBtn.addEventListener('click', useDimensions);

backToScaleBtn.addEventListener('click', () => {
  if (phasePreview._stopAnim) phasePreview._stopAnim();
  showPhase(phaseScale);
  setStep(4);
});
downloadStlBtn.addEventListener('click', triggerDownload);
saveToolBtn.addEventListener('click', saveToolToCatalog);

document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && !scanModal.hidden) closeModal();
});
