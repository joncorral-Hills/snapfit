const brandSelect   = document.getElementById('brand-select');
const modelSelect   = document.getElementById('model-select');
const downloadBtn   = document.getElementById('download-btn');
const specCard      = document.getElementById('spec-card');
const mountSection  = document.getElementById('mount-section');
const statusBar     = document.getElementById('status-bar');
const statusText    = document.getElementById('status-text');
const toast         = document.getElementById('toast');

// Search elements
const searchInput   = document.getElementById('tool-search');
const searchResults = document.getElementById('search-results');
const searchClear   = document.getElementById('search-clear');

let selectedTool = null;
let toastTimer   = null;

// ── Mounting system helpers ───────────────────────────────────────────────────
function getMountingSystem() {
  const checked = document.querySelector('input[name="mounting_system"]:checked');
  return checked ? checked.value : 'magnetic';
}

const MOUNT_LABELS = {
  magnetic:   'Magnetic Panel',
  gridfinity: 'Gridfinity',
  multiboard: 'Multiboard',
  opengrid:   'OpenGrid',
};

function updateDownloadLabel() {
  const sys   = getMountingSystem();
  const label = MOUNT_LABELS[sys] || 'STL';
  downloadBtn.querySelector('svg').nextSibling.textContent = ` Generate ${label} STL`;
  // rewrite as text node cleanly
  const textNodes = [...downloadBtn.childNodes].filter(n => n.nodeType === 3);
  textNodes.forEach(n => n.remove());
  downloadBtn.insertAdjacentText('beforeend', ` Generate ${label} STL`);
}

// Update label when radio changes
document.querySelectorAll('input[name="mounting_system"]').forEach(radio => {
  radio.addEventListener('change', updateDownloadLabel);
});

function showMountSection() {
  if (mountSection) {
    mountSection.hidden = false;
    mountSection.style.display = '';
  }
}

// ── Toast helper ──────────────────────────────────────────────────────────────
function showToast(msg, type = 'success') {
  toast.textContent = msg;
  toast.className = `toast ${type} show`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toast.classList.remove('show'); }, 4000);
}

// ── Spec card renderer ────────────────────────────────────────────────────────
function renderSpec(tool) {
  document.getElementById('spec-brand').textContent     = tool.brand;
  document.getElementById('spec-model').textContent     = tool.model_name;
  document.getElementById('spec-type').textContent      = tool.tool_type;
  document.getElementById('spec-width').textContent     = `${tool.body_width_mm} mm`;
  document.getElementById('spec-depth').textContent     = `${tool.body_depth_mm} mm`;
  document.getElementById('spec-height').textContent    = `${tool.body_height_mm} mm`;
  document.getElementById('spec-handle').textContent    = tool.handle_diameter_mm != null
    ? `Ø${tool.handle_diameter_mm} mm` : '—';
  document.getElementById('spec-weight').textContent    = tool.weight_kg != null
    ? `${tool.weight_kg} kg` : '—';
  specCard.classList.add('visible');
}


// ── Fetch brands on load ──────────────────────────────────────────────────────
async function fetchBrands() {
  try {
    const res  = await fetch('/api/brands');
    const data = await res.json();
    brandSelect.innerHTML = '<option value="">— Select Brand —</option>';
    data.brands.forEach(brand => {
      const opt = document.createElement('option');
      opt.value = brand;
      opt.textContent = brand;
      brandSelect.appendChild(opt);
    });
  } catch (e) {
    showToast('Failed to load brands. Is the server running?', 'error');
  }
}

// ── Fetch models for selected brand ──────────────────────────────────────────
async function fetchModels(brand) {
  modelSelect.innerHTML = '<option value="">Loading…</option>';
  modelSelect.disabled = true;
  downloadBtn.disabled = true;
  specCard.classList.remove('visible');
  selectedTool = null;

  try {
    const res  = await fetch(`/api/tools?brand=${encodeURIComponent(brand)}`);
    const data = await res.json();

    modelSelect.innerHTML = '<option value="">— Select Model —</option>';
    data.tools.forEach(tool => {
      const opt = document.createElement('option');
      opt.value = tool.id;
      opt.dataset.tool = JSON.stringify(tool);
      opt.textContent = tool.model_name;
      modelSelect.appendChild(opt);
    });
    modelSelect.disabled = false;
  } catch (e) {
    modelSelect.innerHTML = '<option value="">Error loading models</option>';
    showToast('Failed to load models.', 'error');
  }
}

// ── Handle brand change ───────────────────────────────────────────────────────
brandSelect.addEventListener('change', () => {
  const brand = brandSelect.value;
  if (!brand) {
    modelSelect.innerHTML = '<option value="">— Select Model —</option>';
    modelSelect.disabled = true;
    downloadBtn.disabled = true;
    specCard.classList.remove('visible');
    return;
  }
  fetchModels(brand);
});

// ── Handle model change ───────────────────────────────────────────────────────
modelSelect.addEventListener('change', () => {
  const selected = modelSelect.options[modelSelect.selectedIndex];
  if (!selected.dataset.tool) {
    downloadBtn.disabled = true;
    specCard.classList.remove('visible');
    selectedTool = null;
    return;
  }
  selectedTool = JSON.parse(selected.dataset.tool);
  renderSpec(selectedTool);
  showMountSection();
  updateDownloadLabel();
  downloadBtn.disabled = false;
});

// ── Handle download ───────────────────────────────────────────────────────────
downloadBtn.addEventListener('click', async () => {
  if (!selectedTool) return;

  downloadBtn.disabled = true;
  statusBar.classList.add('visible');
  statusText.textContent = 'Generating STL…';

  try {
    // 1. Trigger generation
    const mountingSystem = getMountingSystem();
    const genRes = await fetch(`/api/generate/${selectedTool.id}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mounting_system: mountingSystem }),
    });
    if (!genRes.ok) throw new Error(`Generate failed: ${genRes.status}`);
    const { filename } = await genRes.json();

    statusText.textContent = 'Downloading file…';

    // 2. Download the file
    const dlRes = await fetch(`/api/download/${encodeURIComponent(filename)}`);
    if (!dlRes.ok) throw new Error(`Download failed: ${dlRes.status}`);
    const blob = await dlRes.blob();

    // 3. Trigger browser download
    const url  = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);

    showToast(`✓ ${filename} downloaded successfully!`, 'success');
  } catch (err) {
    showToast(`Error: ${err.message}`, 'error');
  } finally {
    downloadBtn.disabled = false;
    statusBar.classList.remove('visible');
  }
});

// ── Submit-your-own form stub ─────────────────────────────────────────────────
const submitForm = document.getElementById('submit-form');
if (submitForm) {
  submitForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(submitForm);
    try {
      const res  = await fetch('/api/submit', { method: 'POST', body: fd });
      const data = await res.json();
      showToast(data.message, 'success');
      submitForm.reset();
    } catch (err) {
      showToast('Submission failed. Please try again.', 'error');
    }
  });
}

// ── Search ────────────────────────────────────────────────────────────────────
let searchTimer  = null;
let searchIndex  = -1;  // keyboard cursor position in results list

function closeSearch() {
  searchResults.hidden = true;
  searchIndex = -1;
}

function selectToolFromSearch(tool) {
  selectedTool = tool;
  renderSpec(tool);
  showMountSection();
  updateDownloadLabel();
  downloadBtn.disabled = false;
  // Reset dropdowns so they don't show a stale selection from a prior pick
  brandSelect.value = '';
  modelSelect.innerHTML = '<option value="">— Select Model —</option>';
  modelSelect.disabled = true;
  searchInput.value = `${tool.brand} — ${tool.model_name}`;
  searchClear.hidden = false;
  closeSearch();
}

function renderSearchResults(tools) {
  searchResults.innerHTML = '';

  if (tools.length === 0) {
    const li = document.createElement('li');
    li.className = 'search-no-results';
    li.textContent = 'No tools found. Try a different keyword.';
    searchResults.appendChild(li);
    searchResults.hidden = false;
    return;
  }

  tools.forEach((tool, i) => {
    const li = document.createElement('li');
    li.className  = 'search-result-item';
    li.role       = 'option';
    li.id         = `sr-${i}`;
    li.innerHTML  = `
      <div class="search-result-info">
        <div class="search-result-name">${tool.model_name}</div>
        <div class="search-result-meta">${tool.brand} · ${tool.tool_type}</div>
      </div>
      <span style="font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--text-muted)">
        ${tool.body_width_mm}×${tool.body_depth_mm}×${tool.body_height_mm} mm
      </span>`;
    li.addEventListener('click', () => selectToolFromSearch(tool));
    searchResults.appendChild(li);
  });

  searchResults.hidden = false;
  searchIndex = -1;
}

function updateKeyboardCursor(newIndex, items) {
  items.forEach((el, i) => el.setAttribute('aria-selected', i === newIndex ? 'true' : 'false'));
  searchIndex = newIndex;
  if (newIndex >= 0) items[newIndex].scrollIntoView({ block: 'nearest' });
}

async function doSearch(query) {
  try {
    const res  = await fetch(`/api/tools?search=${encodeURIComponent(query)}`);
    const data = await res.json();
    renderSearchResults(data.tools);
  } catch {
    renderSearchResults([]);
  }
}

searchInput.addEventListener('input', () => {
  const q = searchInput.value.trim();
  searchClear.hidden = q.length === 0;
  clearTimeout(searchTimer);

  if (q.length === 0) {
    closeSearch();
    return;
  }
  // Debounce 250 ms
  searchTimer = setTimeout(() => doSearch(q), 250);
});

searchInput.addEventListener('keydown', (e) => {
  const items = [...searchResults.querySelectorAll('.search-result-item')];
  if (!items.length) return;
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    updateKeyboardCursor(Math.min(searchIndex + 1, items.length - 1), items);
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    updateKeyboardCursor(Math.max(searchIndex - 1, 0), items);
  } else if (e.key === 'Enter' && searchIndex >= 0) {
    e.preventDefault();
    items[searchIndex].click();
  } else if (e.key === 'Escape') {
    closeSearch();
  }
});

searchClear.addEventListener('click', () => {
  searchInput.value = '';
  searchClear.hidden = true;
  closeSearch();
  // Re-enable spec only if something was already picked via dropdowns
  if (!brandSelect.value) {
    selectedTool = null;
    downloadBtn.disabled = true;
    specCard.classList.remove('visible');
  }
  searchInput.focus();
});

// Close results if clicking outside
document.addEventListener('click', (e) => {
  if (!searchInput.contains(e.target) && !searchResults.contains(e.target)) {
    closeSearch();
  }
});

// ── Camera scan bridge ────────────────────────────────────────────────────────
// Exposed globally so camera.js can inject a scanned tool without coupling.
window.snapfitUseTool = function(tool) {
  selectedTool = tool;
  renderSpec(tool);
  downloadBtn.disabled = false;
  // Show a toast hinting about the custom dimension flow
  showToast('📐 Dimensions loaded. Hit Generate & Download to build your holder.', 'success');
  // Scroll the configurator card into view
  document.querySelector('.card').scrollIntoView({ behavior: 'smooth', block: 'start' });
};

// ── Boot ──────────────────────────────────────────────────────────────────────
fetchBrands();
