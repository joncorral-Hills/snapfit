/**
 * camera.js — SnapFit camera scan module
 *
 * Manages the full "Scan Your Tool" flow:
 *  1. Open modal → start getUserMedia stream (rear cam preferred on mobile)
 *  2. Draw animated guide overlay (dashed bounding rectangle)
 *  3. Capture → freeze frame to canvas
 *  4. POST base64 image to /api/analyze-tool-image
 *  5. Draw contour overlay on captured frame
 *  6. Populate editable dimension inputs
 *  7. "Use These Dimensions" → inject a synthetic tool object into the
 *     existing STL download flow in app.js without touching any existing code
 */

/* ── DOM refs ─────────────────────────────────────────────────────────────── */
const scanModal         = document.getElementById('scan-modal');
const scanBackdrop      = document.getElementById('scan-backdrop');
const scanBtn           = document.getElementById('scan-btn');
const scanClose         = document.getElementById('scan-close');
const scanVideo         = document.getElementById('scan-video');
const guideCanvas       = document.getElementById('scan-guide');
const captureCanvas     = document.getElementById('scan-capture');
const contourCanvas     = document.getElementById('scan-contour');
const overlayMsg        = document.getElementById('scan-overlay-msg');

const ctrlsLive         = document.getElementById('scan-controls-live');
const ctrlsAnalysis     = document.getElementById('scan-controls-analysis');
const ctrlsResult       = document.getElementById('scan-controls-result');

const captureBtn        = document.getElementById('capture-btn');
const retakeBtn         = document.getElementById('retake-btn');
const useDimsBtn        = document.getElementById('use-dims-btn');

const scanDims          = document.getElementById('scan-dims');
const scanWarning       = document.getElementById('scan-warning');
const dimWidth          = document.getElementById('dim-width');
const dimHeight         = document.getElementById('dim-height');
const dimDepth          = document.getElementById('dim-depth');
const dimKnown          = document.getElementById('dim-known');
const dimAxis           = document.getElementById('dim-axis');
const reAnalyseBtn      = document.getElementById('re-analyse-btn');

/* ── State ────────────────────────────────────────────────────────────────── */
let mediaStream   = null;
let guideAnimRAF  = null;
let lastB64       = null;        // most recent captured frame (for re-analyse)

/* ── Guide overlay animation ─────────────────────────────────────────────── */
const GUIDE_PAD  = 0.12;        // fraction of each dimension to inset the guide rect
const DASH_LEN   = 10;
const DASH_GAP   = 6;
let   dashOffset = 0;

function drawGuide() {
  const ctx = guideCanvas.getContext('2d');
  const w   = guideCanvas.width;
  const h   = guideCanvas.height;
  ctx.clearRect(0, 0, w, h);

  const x  = w * GUIDE_PAD;
  const y  = h * GUIDE_PAD;
  const rw = w * (1 - 2 * GUIDE_PAD);
  const rh = h * (1 - 2 * GUIDE_PAD);

  ctx.save();
  ctx.strokeStyle = 'rgba(245,158,11,0.85)';
  ctx.lineWidth   = 2;
  ctx.setLineDash([DASH_LEN, DASH_GAP]);
  ctx.lineDashOffset = -(dashOffset % (DASH_LEN + DASH_GAP));
  ctx.strokeRect(x, y, rw, rh);

  // Corner accents
  const cs = 18;
  ctx.setLineDash([]);
  ctx.strokeStyle = 'rgba(245,158,11,1)';
  ctx.lineWidth   = 3;
  const corners = [
    [[x, y + cs], [x, y], [x + cs, y]],
    [[x + rw - cs, y], [x + rw, y], [x + rw, y + cs]],
    [[x, y + rh - cs], [x, y + rh], [x + cs, y + rh]],
    [[x + rw - cs, y + rh], [x + rw, y + rh], [x + rw - cs, y + rh]],
  ];
  corners.forEach(([a, b, c]) => {
    ctx.beginPath(); ctx.moveTo(...a); ctx.lineTo(...b); ctx.lineTo(...c); ctx.stroke();
  });
  ctx.restore();

  dashOffset += 0.5;
  guideAnimRAF = requestAnimationFrame(drawGuide);
}

function startGuide() {
  syncCanvasSize(guideCanvas);
  drawGuide();
}

function stopGuide() {
  if (guideAnimRAF) { cancelAnimationFrame(guideAnimRAF); guideAnimRAF = null; }
}

function syncCanvasSize(canvas) {
  canvas.width  = canvas.offsetWidth;
  canvas.height = canvas.offsetHeight;
}

/* ── Camera stream ───────────────────────────────────────────────────────── */
async function startCamera() {
  showOverlay('Starting camera…');
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({
      video: {
        facingMode: { ideal: 'environment' },  // rear cam on mobile
        width:  { ideal: 1280 },
        height: { ideal: 960 },
      },
      audio: false,
    });
    scanVideo.srcObject = mediaStream;
    await scanVideo.play();
    hideOverlay();
    startGuide();
  } catch (err) {
    showOverlay(
      err.name === 'NotAllowedError'
        ? '📷 Camera access denied. Allow camera access in your browser settings and try again.'
        : `📷 Could not open camera: ${err.message}`
    );
    ctrlsLive.hidden = true;
  }
}

function stopCamera() {
  stopGuide();
  if (mediaStream) {
    mediaStream.getTracks().forEach(t => t.stop());
    mediaStream = null;
  }
  scanVideo.srcObject = null;
}

/* ── Open / close modal ──────────────────────────────────────────────────── */
function openModal() {
  scanModal.hidden   = false;
  scanBackdrop.hidden = false;
  document.body.style.overflow = 'hidden';
  resetToLivePhase();
  startCamera();
}

function closeModal() {
  stopCamera();
  scanModal.hidden   = true;
  scanBackdrop.hidden = true;
  document.body.style.overflow = '';
}

/* ── Phase transitions ───────────────────────────────────────────────────── */
function resetToLivePhase() {
  // Show video, hide capture canvases
  scanVideo.hidden     = false;
  guideCanvas.hidden   = false;
  captureCanvas.hidden = true;
  contourCanvas.hidden = true;

  // Controls
  ctrlsLive.hidden     = false;
  ctrlsAnalysis.hidden = true;
  ctrlsResult.hidden   = true;

  // Dimensions
  scanDims.hidden    = true;
  scanWarning.hidden = true;

  hideOverlay();
  lastB64 = null;
}

function showAnalysisPhase() {
  // Hide video, show frozen frame
  scanVideo.hidden     = true;
  guideCanvas.hidden   = true;
  captureCanvas.hidden = false;
  contourCanvas.hidden = true;

  ctrlsLive.hidden     = true;
  ctrlsAnalysis.hidden = false;
  ctrlsResult.hidden   = true;
  scanDims.hidden      = true;
}

function showResultPhase(result) {
  contourCanvas.hidden = false;
  ctrlsAnalysis.hidden = true;
  ctrlsResult.hidden   = false;
  scanDims.hidden      = false;

  // Populate dim inputs
  dimWidth.value  = result.width_mm  ?? '';
  dimHeight.value = result.height_mm ?? '';
  // depth stays at user's previous value (default 80)

  // Warning
  if (result.warning) {
    scanWarning.textContent = `⚠️ ${result.warning}`;
    scanWarning.hidden = false;
  } else {
    scanWarning.hidden = true;
  }

  drawContour(result);
}

/* ── Capture & analyse ───────────────────────────────────────────────────── */
function captureFrame() {
  stopGuide();
  syncCanvasSize(captureCanvas);
  const ctx = captureCanvas.getContext('2d');
  ctx.drawImage(scanVideo, 0, 0, captureCanvas.width, captureCanvas.height);

  // Store base64 for re-analysis
  lastB64 = captureCanvas.toDataURL('image/jpeg', 0.9);

  showAnalysisPhase();
  runAnalysis(lastB64);
}

async function runAnalysis(b64) {
  ctrlsAnalysis.hidden = false;
  try {
    const res  = await fetch('/api/analyze-tool-image', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({
        image:              b64,
        known_dimension_mm: parseFloat(dimKnown.value) || 200,
        known_axis:         dimAxis.value,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const result = await res.json();
    showResultPhase(result);
  } catch (err) {
    ctrlsAnalysis.hidden = true;
    ctrlsResult.hidden   = true;
    scanWarning.textContent = `⚠️ Analysis failed: ${err.message}. Retake the photo against a plain background.`;
    scanWarning.hidden      = false;
    scanDims.hidden         = false;
    ctrlsResult.hidden      = false;  // still allow retake
  }
}

/* ── Contour overlay ─────────────────────────────────────────────────────── */
function drawContour(result) {
  syncCanvasSize(contourCanvas);
  const ctx  = contourCanvas.getContext('2d');
  ctx.clearRect(0, 0, contourCanvas.width, contourCanvas.height);

  const scaleX = contourCanvas.width  / captureCanvas.width;
  const scaleY = contourCanvas.height / captureCanvas.height;

  // Contour polygon
  const pts = result.contour_points;
  if (pts && pts.length > 1) {
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(pts[0][0] * scaleX, pts[0][1] * scaleY);
    for (let i = 1; i < pts.length; i++) {
      ctx.lineTo(pts[i][0] * scaleX, pts[i][1] * scaleY);
    }
    ctx.closePath();
    ctx.strokeStyle = 'rgba(245,158,11,0.9)';
    ctx.lineWidth   = 2.5;
    ctx.stroke();
    ctx.fillStyle   = 'rgba(245,158,11,0.07)';
    ctx.fill();
    ctx.restore();
  }

  // Bounding box
  const bb = result.bounding_box;
  if (bb) {
    ctx.save();
    ctx.strokeStyle = 'rgba(52,211,153,0.7)';
    ctx.lineWidth   = 1.5;
    ctx.setLineDash([4, 4]);
    ctx.strokeRect(bb.x * scaleX, bb.y * scaleY, bb.w * scaleX, bb.h * scaleY);
    ctx.restore();
  }

  // Confidence badge
  const conf  = result.confidence ?? 0;
  const color = conf >= 0.6 ? '#34d399' : '#f87171';
  ctx.save();
  ctx.font      = 'bold 12px Inter, sans-serif';
  ctx.fillStyle = color;
  ctx.fillText(`conf: ${(conf * 100).toFixed(0)}%`, 8, 18);
  ctx.restore();
}

/* ── "Use These Dimensions" → feed into STL flow ──────────────────────────── */
function useDimensions() {
  const w = parseFloat(dimWidth.value)  || 80;
  const h = parseFloat(dimHeight.value) || 200;
  const d = parseFloat(dimDepth.value)  || 80;

  // Build a synthetic tool object matching the shape that app.js expects
  const syntheticTool = {
    id:               null,
    brand:            'Custom Scan',
    model_name:       `Scanned Tool (${w}×${d}×${h} mm)`,
    tool_type:        'Custom',
    body_width_mm:    w,
    body_depth_mm:    d,
    body_height_mm:   h,
    handle_diameter_mm: Math.round(d * 0.4),  // rough estimate
    weight_kg:        null,
  };

  closeModal();

  // Delegate to the existing app.js function (exposed via globalThis)
  if (typeof window.snapfitUseTool === 'function') {
    window.snapfitUseTool(syntheticTool);
  }
}

/* ── Overlay helpers ─────────────────────────────────────────────────────── */
function showOverlay(msg) {
  overlayMsg.textContent = msg;
  overlayMsg.hidden = false;
}

function hideOverlay() {
  overlayMsg.hidden = true;
}

/* ── Event listeners ─────────────────────────────────────────────────────── */
scanBtn.addEventListener('click', openModal);
scanClose.addEventListener('click', closeModal);
scanBackdrop.addEventListener('click', closeModal);

captureBtn.addEventListener('click', captureFrame);

retakeBtn.addEventListener('click', () => {
  resetToLivePhase();
  startCamera();
});

reAnalyseBtn.addEventListener('click', () => {
  if (!lastB64) return;
  showAnalysisPhase();
  captureCanvas.hidden = false;
  runAnalysis(lastB64);
});

useDimsBtn.addEventListener('click', useDimensions);

// Escape key closes modal
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !scanModal.hidden) closeModal();
});

// Resize: keep guide canvas in sync
window.addEventListener('resize', () => {
  if (!scanModal.hidden && !guideCanvas.hidden) {
    syncCanvasSize(guideCanvas);
  }
});
