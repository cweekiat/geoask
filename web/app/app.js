/* GeoAsk Investigator — map + Ask panel.
   Live mode talks to `geoask serve` (/api/*). On GitHub Pages there is no server, so the app runs in
   Demo mode and replays a precomputed result. Everything else (map, layers, timeline) works the same. */
(() => {
  'use strict';

  // ---------- icons: drawn for GeoAsk (24px grid, 1.75 stroke, round joins). Not SF Symbols. ----------
  const ICONS = {
    search: '<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/>',
    layers: '<path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m3 13 9 5 9-5"/>',
    globe: '<circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="4" ry="9"/><path d="M3 12h18"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    minus: '<path d="M5 12h14"/>',
    compass: '<circle cx="12" cy="12" r="9"/><path d="m15.5 8.5-2 5-5 2 2-5 5-2Z"/>',
    home: '<path d="M4 11 12 4l8 7"/><path d="M6 10v9h12v-9"/>',
    'panel-left': '<rect x="3.5" y="4.5" width="17" height="15" rx="3"/><path d="M9.5 4.5v15"/>',
    'plus-square': '<rect x="4" y="4" width="16" height="16" rx="4"/><path d="M12 8.5v7M8.5 12h7"/>',
    'arrow-up': '<path d="M12 19V6M6.5 11.5 12 6l5.5 5.5"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5"/><circle cx="12" cy="7.8" r=".6" fill="currentColor"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    message: '<path d="M5 5h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-7l-5 4v-4H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z"/>',
    pin: '<path d="M12 21s6.5-6 6.5-11.5a6.5 6.5 0 1 0-13 0C5.5 15 12 21 12 21Z"/><circle cx="12" cy="9.5" r="2.3"/>',
    check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
    down: '<path d="M12 5v14M6 13l6 6 6-6"/>',
    up: '<path d="M12 19V5M6 11l6-6 6 6"/>',
    target: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/>',
    compare: '<rect x="3.5" y="5" width="17" height="14" rx="2.5"/><path d="M12 3v18"/>',
    thumbup: '<path d="M7 11v9H4v-9h3Zm0 0 4-7a2 2 0 0 1 2 2v4h5a2 2 0 0 1 2 2.3l-1.2 6A2 2 0 0 1 16.8 20H7"/>',
    thumbdown: '<path d="M7 13V4H4v9h3Zm0 0 4 7a2 2 0 0 0 2-2v-4h5a2 2 0 0 0 2-2.3l-1.2-6A2 2 0 0 0 16.8 4H7"/>',
    retry: '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 5v6h-6"/>',
    select: '<path d="M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3"/><path d="M10 4h4M10 20h4M4 10v4M20 10v4"/>',
    x: '<path d="M6 6l12 12M18 6 6 18"/>',
    sparkle: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6.3 6.3l2.5 2.5M15.2 15.2l2.5 2.5M6.3 17.7l2.5-2.5M15.2 8.8l2.5-2.5"/>',
  };
  const icon = (n, cls = 'icon') => `<svg class="${cls}" viewBox="0 0 24 24" aria-hidden="true">${ICONS[n] || ''}</svg>`;
  document.querySelectorAll('svg[data-icon]').forEach(el => {
    el.setAttribute('viewBox', '0 0 24 24'); el.setAttribute('aria-hidden', 'true');
    el.innerHTML = ICONS[el.dataset.icon] || '';
  });

  // ---------- state ----------
  const $ = s => document.querySelector(s);
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const SG = { center: [103.8198, 1.3521], bounds: [[103.59, 1.15], [104.1, 1.48]] };
  const FALLBACK_PLACES = {
    tengah: [103.715, 1.345, 103.755, 1.375], tuas: [103.6, 1.22, 103.68, 1.34],
    'pulau tekong': [103.95, 1.38, 104.06, 1.43], 'jurong island': [103.66, 1.24, 103.73, 1.3],
    punggol: [103.89, 1.39, 103.93, 1.42], 'changi airport': [103.97, 1.33, 104.01, 1.4],
    'marina bay': [103.85, 1.27, 103.87, 1.3], 'central catchment': [103.78, 1.34, 103.83, 1.4],
  };
  const EXAMPLES = [
    'What changed in Tengah since 2019?',
    'How much vegetation did Tengah lose between 2019 and 2026?',
    'How has the coastline at Tuas changed since 2018?',
    'How much new built-up land is there in Punggol since 2019?',
  ];
  const DEMO_BASE = '../gallery/tengah/';
  let live = false, places = FALLBACK_PLACES, active = null, busy = false, selection = null;

  // ---------- map ----------
  const eox = y => `https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-${y}_3857/default/g/{z}/{y}/{x}.jpg`;
  const S2_ATTR = '<a href="https://s2maps.eu" target="_blank" rel="noopener">Sentinel-2 cloudless</a> by EOX (Copernicus Sentinel data)';
  const map = new maplibregl.Map({
    container: 'map',
    style: 'https://tiles.openfreemap.org/styles/fiord',
    center: SG.center, zoom: reduceMotion ? 10.8 : 1.8,
    attributionControl: { compact: true }, maxPitch: 75,
  });
  map.addControl(new maplibregl.ScaleControl({ unit: 'metric', maxWidth: 110 }), 'bottom-right');

  let labelLayers = [];
  map.on('style.load', () => {
    try { map.setProjection({ type: 'globe' }); } catch (e) { /* older engines: stay flat */ }
    const layers = map.getStyle().layers;
    labelLayers = layers.filter(l => l.type === 'symbol').map(l => l.id);
    const firstSymbol = labelLayers[0];

    map.addSource('s2', { type: 'raster', tiles: [eox(2025)], tileSize: 256, maxzoom: 15, attribution: S2_ATTR });
    map.addSource('hires', {
      type: 'raster', tileSize: 256, maxzoom: 19,
      tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
      attribution: 'Imagery © Esri, Maxar, Earthstar Geographics',
    });
    map.addSource('dem', {
      type: 'raster-dem', encoding: 'terrarium', tileSize: 256, maxzoom: 15,
      tiles: ['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'],
      attribution: 'Terrain: Mapzen / AWS Terrain Tiles',
    });
    map.addLayer({ id: 's2', type: 'raster', source: 's2', paint: { 'raster-fade-duration': 150 } }, firstSymbol);
    map.addLayer({ id: 'hires', type: 'raster', source: 'hires', layout: { visibility: 'none' } }, firstSymbol);

    map.addSource('areas', { type: 'geojson', data: areasGeoJSON() });
    map.addLayer({ id: 'areas-fill', type: 'fill', source: 'areas', paint: { 'fill-color': '#5aa9ff', 'fill-opacity': 0.04 } });
    map.addLayer({ id: 'areas-line', type: 'line', source: 'areas',
      paint: { 'line-color': '#8cc2ff', 'line-width': 1.2, 'line-dasharray': [3, 2], 'line-opacity': 0.75 } });
    map.addLayer({ id: 'areas-label', type: 'symbol', source: 'areas', minzoom: 10.5,
      layout: { 'text-field': ['get', 'title'], 'text-size': 12, 'text-font': ['Noto Sans Regular'], 'text-anchor': 'top-left', 'text-offset': [0.4, 0.4] },
      paint: { 'text-color': '#cfe3ff', 'text-halo-color': '#070b12', 'text-halo-width': 1.4 } });
    map.addSource('sel', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
    map.addLayer({ id: 'sel-fill', type: 'fill', source: 'sel', paint: { 'fill-color': '#5aa9ff', 'fill-opacity': 0.12 } });
    map.addLayer({ id: 'sel-line', type: 'line', source: 'sel', paint: { 'line-color': '#8cc2ff', 'line-width': 2 } });
    map.on('click', 'areas-fill', e => { if (!drawing) focusPlace(e.features[0].properties.name); });
    map.on('mouseenter', 'areas-fill', () => map.getCanvas().style.cursor = 'pointer');
    map.on('mouseleave', 'areas-fill', () => map.getCanvas().style.cursor = '');

    if (!reduceMotion) setTimeout(() => map.flyTo({ center: SG.center, zoom: 10.8, duration: 3200, essential: false }), 400);
  });
  map.on('error', e => { if (String(e?.error?.message || '').includes('styles/fiord')) toast('Map style unavailable — check your connection.'); });

  map.on('mousemove', e => {
    const { lng, lat } = e.lngLat;
    $('#hud').textContent = `${Math.abs(lat).toFixed(4)}° ${lat >= 0 ? 'N' : 'S'}  ${lng.toFixed(4)}° E   z${map.getZoom().toFixed(1)}`;
  });

  function areasGeoJSON() {
    return { type: 'FeatureCollection', features: Object.entries(places).map(([name, [w, s, e, n]]) => ({
      type: 'Feature', properties: { name, title: titleCase(name) },
      geometry: { type: 'Polygon', coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] } })) };
  }
  const titleCase = s => s.replace(/\b\w/g, c => c.toUpperCase());

  // ---------- rail ----------
  $('#btn-zin').onclick = () => map.zoomIn();
  $('#btn-zout').onclick = () => map.zoomOut();
  $('#btn-north').onclick = () => map.easeTo({ bearing: 0, pitch: 0, duration: reduceMotion ? 0 : 500 });
  $('#btn-home').onclick = () => map.fitBounds(SG.bounds, { padding: pad(), duration: reduceMotion ? 0 : 900 });
  $('#btn-globe').onclick = e => {
    const on = e.currentTarget.getAttribute('aria-pressed') !== 'true';
    e.currentTarget.setAttribute('aria-pressed', on);
    if (on) { map.setTerrain({ source: 'dem', exaggeration: 1.6 }); map.easeTo({ pitch: 62, bearing: -20, duration: reduceMotion ? 0 : 900 }); }
    else { map.setTerrain(null); map.easeTo({ pitch: 0, bearing: 0, duration: reduceMotion ? 0 : 700 }); }
  };

  const pad = () => {
    const collapsed = document.body.classList.contains('panel-collapsed');
    const narrow = innerWidth <= 760;
    return narrow ? { top: 80, bottom: collapsed ? 140 : innerHeight * 0.58 + 40, left: 30, right: 70 }
      : { top: 80, bottom: 110, left: collapsed ? 60 : 470, right: 80 };
  };

  // ---------- draw an area ----------
  let drawing = false, drawStart = null;
  const boxFeature = b => ({ type: 'FeatureCollection', features: b ? [{ type: 'Feature', properties: {},
    geometry: { type: 'Polygon', coordinates: [[[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]], [b[0], b[1]]]] } }] : [] });
  const bboxKm2 = ([w, s, e, n]) => (e - w) * 111.32 * Math.cos((s + n) / 2 * Math.PI / 180) * (n - s) * 110.57;
  function setDrawing(on) {
    drawing = on; document.body.classList.toggle('drawing', on);
    $('#btn-draw').setAttribute('aria-pressed', on); $('#draw-hint').hidden = !on;
    on ? map.dragPan.disable() : map.dragPan.enable();
    if (on) $('#draw-view').focus();
  }
  function setSelection(b) {
    selection = b ? b.map(v => +v.toFixed(5)) : null;
    map.getSource('sel')?.setData(boxFeature(selection));
    const chip = $('#selection');
    chip.hidden = !selection;
    if (selection) {
      $('#sel-text').textContent = `Selected area · ${bboxKm2(selection).toFixed(1)} km²`;
      if (!askBox.value.trim()) { askBox.value = 'What is being built here?'; askBox.dispatchEvent(new Event('input')); }
      askBox.focus();
    }
  }
  $('#btn-draw').onclick = () => setDrawing(!drawing);
  $('#draw-cancel').onclick = () => setDrawing(false);
  $('#draw-view').onclick = () => {  // keyboard/touch alternative to dragging
    const b = map.getBounds();
    const w = b.getWest(), e = b.getEast(), s = b.getSouth(), n = b.getNorth();
    const cx = (w + e) / 2, cy = (s + n) / 2, hw = (e - w) * 0.3, hh = (n - s) * 0.3;
    setSelection([cx - hw, cy - hh, cx + hw, cy + hh]); setDrawing(false);
  };
  $('#sel-clear').onclick = () => setSelection(null);
  map.on('mousedown', e => { if (!drawing) return; drawStart = e.lngLat; e.preventDefault(); });
  map.on('touchstart', e => { if (!drawing || e.points.length !== 1) return; drawStart = e.lngLat; e.preventDefault(); });
  const dragTo = e => {
    if (!drawing || !drawStart) return;
    const b = [Math.min(drawStart.lng, e.lngLat.lng), Math.min(drawStart.lat, e.lngLat.lat), Math.max(drawStart.lng, e.lngLat.lng), Math.max(drawStart.lat, e.lngLat.lat)];
    map.getSource('sel').setData(boxFeature(b));
    return b;
  };
  map.on('mousemove', dragTo); map.on('touchmove', dragTo);
  const finish = e => {
    if (!drawing || !drawStart) return;
    const b = dragTo(e); drawStart = null;
    if (b && bboxKm2(b) > 0.05) { setSelection(b); setDrawing(false); }
    else map.getSource('sel').setData(boxFeature(selection));
  };
  map.on('mouseup', finish); map.on('touchend', finish);

  // ---------- layers popover ----------
  const lp = $('#layers'), lb = $('#btn-layers');
  const setLayers = open => { lp.hidden = !open; lb.setAttribute('aria-expanded', open); lb.setAttribute('aria-pressed', open); if (open) lp.querySelector('input:checked')?.focus(); };
  lb.onclick = () => setLayers(lp.hidden);
  document.addEventListener('pointerdown', e => { if (!lp.hidden && !lp.contains(e.target) && !lb.contains(e.target)) setLayers(false); });
  lp.querySelectorAll('input[name=base]').forEach(r => r.onchange = () => {
    const v = lp.querySelector('input[name=base]:checked').value;
    map.setLayoutProperty('s2', 'visibility', v === 's2' ? 'visible' : 'none');
    map.setLayoutProperty('hires', 'visibility', v === 'hires' ? 'visible' : 'none');
    $('#timeline').style.display = (v === 's2' || active) ? '' : 'none';
  });
  $('#ov-labels').onchange = e => labelLayers.forEach(id => map.setLayoutProperty(id, 'visibility', e.target.checked ? 'visible' : 'none'));
  $('#ov-areas').onchange = e => ['areas-fill', 'areas-line', 'areas-label'].forEach(id => map.setLayoutProperty(id, 'visibility', e.target.checked ? 'visible' : 'none'));
  $('#ov-change').onchange = e => map.getLayer('res-delta') && map.setLayoutProperty('res-delta', 'visibility', e.target.checked ? 'visible' : 'none');

  // ---------- timeline ----------
  const tl = $('#tl');
  function yearMode() {
    tl.min = 2017; tl.max = 2025; tl.step = 1; tl.value = 2025;
    $('#tl-kind').textContent = 'Imagery year'; $('#tl-label').textContent = 'Imagery year';
    $('#tl-value').textContent = '2025';
    $('#ticks').innerHTML = Array.from({ length: 9 }, (_, i) => `<span>${i % 2 ? '' : 2017 + i}</span>`).join('');
    tl.setAttribute('aria-valuetext', '2025');
  }
  function compareMode(r) {
    tl.min = 0; tl.max = 100; tl.step = 1; tl.value = 100;
    $('#tl-kind').textContent = 'Before ↔ After'; $('#tl-label').textContent = 'Blend between before and after imagery';
    $('#ticks').innerHTML = `<span>${r.date0}</span><span>${r.date1}</span>`;
    updateCompare();
  }
  function updateCompare() {
    const t = +tl.value / 100;
    if (map.getLayer('res-after')) map.setPaintProperty('res-after', 'raster-opacity', t);
    if (map.getLayer('res-before')) map.setPaintProperty('res-before', 'raster-opacity', 1);
    const label = t > 0.5 ? active.date1 : active.date0;
    $('#tl-value').textContent = label;
    tl.setAttribute('aria-valuetext', `${Math.round(t * 100)}% after (${label})`);
  }
  tl.oninput = () => {
    if (active) return updateCompare();
    $('#tl-value').textContent = tl.value; tl.setAttribute('aria-valuetext', tl.value);
    map.getSource('s2')?.setTiles([eox(tl.value)]);
  };
  yearMode();

  // ---------- search ----------
  const q = $('#q'), results = $('#results'), search = $('#search');
  let sel = -1, items = [];
  let found = {}, searchSeq = 0;
  async function renderResults() {
    const term = q.value.trim().toLowerCase();
    if (live) {
      const my = ++searchSeq;
      try {
        const rs = await (await fetch('/api/search?q=' + encodeURIComponent(term))).json();
        if (my !== searchSeq) return;
        found = Object.fromEntries(rs.map(r => [r.name, r.bbox]));
      } catch { found = {}; }
    } else {
      found = Object.fromEntries(Object.entries(places).filter(([n]) => !term || n.includes(term)).slice(0, 8));
    }
    items = Object.keys(found);
    results.innerHTML = items.map((n, i) => `<li role="option" id="opt-${i}" aria-selected="${i === sel}" data-name="${esc(n)}">${icon('pin', 'icon sm')}<span>${esc(titleCase(n))}</span><span class="meta">${approxKm2(found[n])} km²</span></li>`).join('')
      || `<li role="option" aria-disabled="true">No match. Try another name, or draw an area.</li>`;
    results.hidden = false; search.setAttribute('aria-expanded', 'true');
    q.setAttribute('aria-activedescendant', sel >= 0 ? `opt-${sel}` : '');
  }
  const approxKm2 = ([w, s, e, n]) => ((e - w) * 111.32 * (n - s) * 110.57).toFixed(1);
  const closeResults = () => { results.hidden = true; search.setAttribute('aria-expanded', 'false'); sel = -1; };
  q.addEventListener('focus', renderResults);
  q.addEventListener('input', () => { sel = -1; renderResults(); });
  q.addEventListener('keydown', e => {
    if (e.key === 'ArrowDown') { sel = Math.min(sel + 1, items.length - 1); renderResults(); e.preventDefault(); }
    else if (e.key === 'ArrowUp') { sel = Math.max(sel - 1, 0); renderResults(); e.preventDefault(); }
    else if (e.key === 'Enter') { const n = items[Math.max(sel, 0)]; if (n) { focusPlace(n); closeResults(); q.blur(); } }
    else if (e.key === 'Escape') { closeResults(); q.blur(); }
  });
  results.addEventListener('pointerdown', e => { const li = e.target.closest('li[data-name]'); if (li) { e.preventDefault(); focusPlace(li.dataset.name); closeResults(); q.blur(); } });
  q.addEventListener('blur', () => setTimeout(closeResults, 120));

  function focusPlace(name) {
    const [w, s, e, n] = found[name] || places[name];
    q.value = titleCase(name);
    map.fitBounds([[w, s], [e, n]], { padding: pad(), duration: reduceMotion ? 0 : 1100, maxZoom: 15 });
    const ask = $('#ask');
    if (!ask.value.trim()) { ask.value = `How much vegetation did ${titleCase(name)} lose since 2019?`; ask.dispatchEvent(new Event('input')); }
  }

  // ---------- panel ----------
  const panel = $('#panel');
  const setCollapsed = c => {
    panel.dataset.collapsed = c; document.body.classList.toggle('panel-collapsed', c);
    if (!c) $('#ask').focus({ preventScroll: true });
  };
  $('#collapse').onclick = () => setCollapsed(true);
  $('#fab').onclick = () => setCollapsed(false);
  $('#new-chat').onclick = () => { clearResult(); log.innerHTML = ''; renderEmpty(); };

  const log = $('#log');
  function renderEmpty() {
    log.innerHTML = `<div class="empty">
      <h2>What would you like to investigate?</h2>
      <p>Ask how an area of Singapore has changed. GeoAsk finds the clearest satellite images, measures the change and shows it on the map.</p>
      <div class="chips">${EXAMPLES.map(x => `<button class="chip" type="button">${esc(x)}</button>`).join('')}</div></div>`;
    log.querySelectorAll('.chip').forEach(b => b.onclick = () => ask(b.textContent));
  }

  // composer
  const askBox = $('#ask'), send = $('#send');
  askBox.addEventListener('input', () => {
    send.disabled = busy || !askBox.value.trim();
    askBox.style.height = 'auto'; askBox.style.height = Math.min(askBox.scrollHeight, 120) + 'px';
    askBox.classList.toggle('scroll', askBox.scrollHeight > 120);
  });
  askBox.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); $('#ask-form').requestSubmit(); } });
  $('#ask-form').addEventListener('submit', e => { e.preventDefault(); const t = askBox.value.trim(); if (t && !busy) ask(t); });

  // ---------- asking ----------
  async function ask(question) {
    busy = true; send.disabled = true;
    log.querySelector('.empty')?.remove();
    const box = selection;
    log.insertAdjacentHTML('beforeend', `<div class="msg-user">${esc(question)}${box ? `<br><small>${icon('select', 'icon sm')} selected area</small>` : ''}</div>`);
    askBox.value = ''; askBox.dispatchEvent(new Event('input'));
    const bot = document.createElement('div'); bot.className = 'msg-bot'; log.appendChild(bot);
    const ctx = { bot, steps: null, question, box };
    try {
      if (live) await askLive(question, ctx); else await askDemo(question, ctx);
    } catch (err) {
      showError(ctx, `Couldn't reach GeoAsk: ${err.message}`, 'Make sure `geoask serve` is still running, then try again.');
    } finally {
      busy = false; send.disabled = !askBox.value.trim(); finishSteps(ctx);
      log.scrollTop = log.scrollHeight;
    }
  }

  async function askLive(question, ctx) {
    const res = await fetch('/api/ask', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question, bbox: ctx.box }) });
    if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
    const reader = res.body.getReader(), dec = new TextDecoder();
    let buf = '';
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf('\n')) >= 0) { const line = buf.slice(0, i); buf = buf.slice(i + 1); if (line.trim()) handle(JSON.parse(line), ctx); }
    }
  }

  function handle(ev, ctx) {
    if (ev.type === 'plan') {
      showPlan(ctx, ev);
      const b = ev.args?.bbox || places[ev.args?.place];
      if (b) map.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: pad(), duration: reduceMotion ? 0 : 1100, maxZoom: 15 });
    }
    else if (ev.type === 'step') addStep(ctx, ev.text);
    else if (ev.type === 'result') showResult(ctx, ev.result, ev.result.base);
    else if (ev.type === 'clarify') showClarify(ctx, ev.message, ev.suggestions);
    else if (ev.type === 'reply') showClarify(ctx, ev.message, ev.suggestions);
    else if (ev.type === 'answer') showAnswer(ctx, ev.text, ev.source);
    else if (ev.type === 'error') showError(ctx, ev.message, ev.hint);
    log.scrollTop = log.scrollHeight;
  }

  function showPlan(ctx, p) {
    const args = Object.entries(p.args).map(([k, v]) => `${k}=<b>${esc(v)}</b>`).join(', ');
    const html = `<p>${esc(p.explanation)}</p><div class="plan" aria-label="Analysis plan">${esc(p.tool)}(${args})<br><span>planned by ${esc(p.planner)}</span></div>`;
    if (ctx.steps) ctx.steps.insertAdjacentHTML('beforebegin', html);  // keep one ordered step list below the plan
    else { ctx.bot.insertAdjacentHTML('beforeend', html + '<ul class="steps"></ul>'); ctx.steps = ctx.bot.querySelector('.steps'); }
  }
  function addStep(ctx, text) {
    if (!ctx.steps) { ctx.bot.insertAdjacentHTML('beforeend', '<ul class="steps"></ul>'); ctx.steps = ctx.bot.querySelector('.steps'); }
    finishSteps(ctx, true);
    ctx.steps.insertAdjacentHTML('beforeend', `<li><span class="dot"><span class="spinner" role="img" aria-label="In progress"></span></span><span>${esc(text)}…</span></li>`);
  }
  function finishSteps(ctx) {
    ctx.steps?.querySelectorAll('li:not(.done)').forEach(li => { li.classList.add('done'); li.querySelector('.dot').innerHTML = icon('check', 'icon sm'); li.lastElementChild.textContent = li.lastElementChild.textContent.replace(/…$/, ''); });
  }
  function showAnswer(ctx, text, source) {
    finishSteps(ctx);
    const by = source.startsWith('template') ? `Fixed wording${source.includes('number check') ? ': the model’s wording failed the number check' : ''}` : `Written by ${source} on this computer from the measurements`;
    const el = document.createElement('div'); el.className = 'answer';
    el.innerHTML = `<p>${esc(text)}</p><div class="src">${icon('sparkle', 'icon sm')}${esc(by)}</div>`;
    const card = ctx.bot.querySelector('.card');
    card ? ctx.bot.insertBefore(el, card) : ctx.bot.appendChild(el);
  }
  function showClarify(ctx, message, suggestions = []) {
    ctx.bot.insertAdjacentHTML('beforeend', `<p>${esc(message)}</p><div class="chips">${suggestions.map(s => `<button class="chip" type="button">${esc(s)}</button>`).join('')}</div>`);
    ctx.bot.querySelectorAll('.chip').forEach(b => b.onclick = () => ask(b.textContent));
  }
  function showError(ctx, message, hint) {
    finishSteps(ctx);
    ctx.bot.insertAdjacentHTML('beforeend', `<div class="card error" role="alert"><h3>Couldn't finish this analysis</h3><p>${esc(message)}</p>${hint ? `<p class="method">${esc(hint)}</p>` : ''}<div class="actions"><button class="btn retry" type="button">${icon('retry', 'icon sm')}Try Again</button></div></div>`);
    ctx.bot.querySelector('.retry:last-of-type').onclick = () => ask(ctx.question);
  }

  const fmtHa = n => `${Math.round(n).toLocaleString()} ha`;
  const itemUrl = id => `https://earth-search.aws.element84.com/v1/collections/sentinel-2-l2a/items/${encodeURIComponent(id)}`;

  function showResult(ctx, r, base) {
    finishSteps(ctx);
    const idx = r.index.toUpperCase();
    const sources = r.picks.map((p, i) => `<li>${i ? 'After' : 'Before'} ${esc(p.date)} · ${Math.round(p.clear * 100)}% clear<br>${p.scenes.map(s => `<a href="${itemUrl(s)}" target="_blank" rel="noopener">${esc(s)}</a>`).join('<br>')}</li>`).join('');
    const fm = r.tool === 'embedding_change';
    const card = document.createElement('div'); card.className = 'card';
    const stats = fm ? `
        <div class="stat fm"><div class="v">${icon('target', 'icon sm')}${fmtHa(r.changed_ha)}</div><div class="k">Changed (any kind)</div></div>
        <div class="stat"><div class="v">${r.patch_m} m</div><div class="k">Patch size</div></div>
        <div class="stat"><div class="v">${r.threshold.toFixed(2)}</div><div class="k">Change threshold (Otsu)</div></div>
        <div class="stat"><div class="v">${Math.round(r.compared_fraction * 100)}%</div><div class="k">Area clear on both dates</div></div>` : `
        <div class="stat loss"><div class="v">${icon('down', 'icon sm')}${fmtHa(r.loss_ha)}</div><div class="k">${esc(r.label)} lost</div></div>
        <div class="stat gain"><div class="v">${icon('up', 'icon sm')}${fmtHa(r.gain_ha)}</div><div class="k">${esc(r.label)} gained</div></div>
        <div class="stat"><div class="v">${r.mean0.toFixed(2)} → ${r.mean1.toFixed(2)}</div><div class="k">Mean ${idx}</div></div>
        <div class="stat"><div class="v">${Math.round(r.compared_fraction * 100)}%</div><div class="k">Area clear on both dates</div></div>`;
    const legend = fm
      ? `<span><i class="sw" style="background:linear-gradient(90deg,#5aa9ff,#fff)"></i>Changed: brighter means a bigger change</span>`
      : `<span><i class="sw" style="background:#ff7a45"></i>Decrease (loss)</span><span><i class="sw" style="background:#34d1c4"></i>Increase (gain)</span>`;
    const method = fm
      ? `${esc(r.model)} embeds each 2.56 km chip on both dates. Every ${r.patch_m} m patch is compared by cosine distance, and patches above an Otsu threshold count as changed. This finds change of any kind (construction, clearing, new water) without choosing an index.`
      : `${idx} is computed from native ${r.grid.res_m} m pixels on dates chosen by the most clear pixels inside the area. Loss counts pixels that crossed from a high to a low ${idx}.`;
    card.innerHTML = `
      <h3>${fm ? 'Any change' : esc(titleCase(r.label)) + ' change'} · ${r.place_source === 'drawn' ? 'Selected area' : esc(titleCase(r.place))}</h3>
      <div class="when">${esc(r.date0)} → ${esc(r.date1)} · ${esc(fm ? r.model : r.sensor)} · ${r.grid.res_m} m</div>
      <div class="stats">${stats}
      </div>
      <div class="legend">${legend}</div>
      <div class="actions">
        <button class="btn primary act-show" type="button">${icon('target', 'icon sm')}Show on Map</button>
        <button class="btn act-compare" type="button">${icon('compare', 'icon sm')}Compare Before/After</button>
      </div>
      <details><summary>Sources and method</summary>
        <ul>${sources}</ul>
        <p class="method">${method} ${r.place_bbox_approximate ? 'The area outline is approximate.' : ''}</p>
      </details>
      <div class="feedback"><span>Was this useful?</span>
        <button class="btn-icon fb" aria-label="Useful" aria-pressed="false">${icon('thumbup', 'icon sm')}</button>
        <button class="btn-icon fb" aria-label="Not useful" aria-pressed="false">${icon('thumbdown', 'icon sm')}</button>
        <span class="fb-note" role="status"></span></div>`;
    ctx.bot.appendChild(card);
    card.querySelector('.act-show').onclick = () => showOnMap(r, base, false);
    card.querySelector('.act-compare').onclick = () => showOnMap(r, base, true);
    card.querySelectorAll('.fb').forEach(b => b.onclick = () => {
      card.querySelectorAll('.fb').forEach(x => x.setAttribute('aria-pressed', x === b));
      card.querySelector('.fb-note').textContent = 'Thanks. Feedback stays on this device.';
    });
    showOnMap(r, base, false);
  }

  // ---------- result overlays ----------
  function clearResult() {
    ['res-delta', 'res-after', 'res-before'].forEach(id => { if (map.getLayer(id)) map.removeLayer(id); if (map.getSource(id)) map.removeSource(id); });
    active = null; yearMode();
    const ov = $('#ov-change'); ov.disabled = true; $('#ov-change-d').textContent = 'Ask a question to create one';
  }
  function showOnMap(r, base, compare) {
    clearResult(); active = r;
    const before = labelLayers[0] && map.getLayer('areas-fill') ? 'areas-fill' : undefined;
    const add = (id, file, paint, vis = 'visible') => {
      map.addSource(id, { type: 'image', url: base + file, coordinates: r.corners });
      map.addLayer({ id, type: 'raster', source: id, layout: { visibility: vis }, paint: { 'raster-fade-duration': 0, ...paint } }, before);
    };
    add('res-before', r.images.before, {});
    add('res-after', r.images.after, {});
    add('res-delta', r.images.delta, { 'raster-opacity': 0.9 }, compare ? 'none' : 'visible');
    const ov = $('#ov-change'); ov.disabled = false; ov.checked = !compare; $('#ov-change-d').textContent = `${r.index.toUpperCase()} ${r.date0} → ${r.date1}`;
    $('#timeline').style.display = '';
    compareMode(r);
    if (compare) { tl.value = 0; updateCompare(); tl.focus(); toast('Drag the timeline to blend from before to after.'); }
    const lons = r.corners.map(c => c[0]), lats = r.corners.map(c => c[1]);
    map.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]], { padding: pad(), duration: reduceMotion ? 0 : 1200 });
  }

  // ---------- demo mode (GitHub Pages: no server) ----------
  const sleep = ms => new Promise(r => setTimeout(r, reduceMotion ? 0 : ms));
  async function askDemo(question, ctx) {
    const named = Object.keys(places).find(p => question.toLowerCase().includes(p));
    if (named && named !== 'tengah') {
      ctx.bot.insertAdjacentHTML('beforeend', `<p>This demo can't run new analyses, because GitHub Pages has no server. Run GeoAsk on your Mac or Linux machine to ask about ${esc(titleCase(named))}:</p><div class="plan">uv pip install -e ".[serve]"<br>geoask serve</div><p>Here is a precomputed example instead.</p>`);
    }
    // A topic word picks the NDVI example; an open "what changed" question picks the Clay one.
    const topic = /vegetat|forest|green|tree|park|water|coast|built|construct/i.test(question);
    const base = topic ? DEMO_BASE : '../gallery/tengah-clay/';
    const r = await (await fetch(base + 'result.json')).json();
    const t = { t0: '2019-01-01/2019-12-31', t1: '2026-01-01/2026-11-20' };
    if (topic) showPlan(ctx, { tool: 'index_change', planner: 'rule-based (demo replay)', explanation: 'Compare vegetation (NDVI) over Tengah: clearest date in 2019 vs clearest date in 2026.', args: { place: 'tengah', index: 'ndvi', ...t } });
    else showPlan(ctx, { tool: 'embedding_change', planner: 'rule-based (demo replay)', explanation: 'Look for any kind of change over Tengah with the Clay foundation model: clearest date in 2019 vs clearest date in 2026.', args: { place: 'tengah', model: 'clay-v1.5', ...t } });
    const steps = topic
      ? ['Searching Sentinel-2 scenes over Tengah, 2019', 'Ranking 64 scenes by clear pixels inside Tengah, then re-checking the best for haze', `Reading 4 bands at 10 m for ${r.date0}`, 'Searching and ranking 2026 scenes', `Reading 4 bands at 10 m for ${r.date1}`, 'Computing NDVI change']
      : ['Loading Clay on this device', 'Finding the clearest before date over Tengah', `Reading 10 bands for ${r.date0}`, `Embedding ${r.date0} with clay-v1.5`, 'Finding the clearest after date', `Embedding ${r.date1} with clay-v1.5`, 'Comparing embeddings patch by patch'];
    for (const s of steps) {
      addStep(ctx, s); log.scrollTop = log.scrollHeight; await sleep(450);
    }
    showResult(ctx, r, base);
  }

  // ---------- boot ----------
  function setMode(isLive) {
    live = isLive;
    const m = $('#mode');
    m.textContent = isLive ? 'Live' : 'Demo';
    m.className = 'mode-chip ' + (isLive ? 'live' : 'demo');
    m.title = isLive ? 'Connected to geoask serve: answers are computed now' : 'No server here: answers are precomputed. Run geoask serve for live analysis.';
  }
  (async () => {
    try {
      const ctrl = new AbortController(); setTimeout(() => ctrl.abort(), 2500);
      const h = await fetch('/api/health', { signal: ctrl.signal });
      if (!h.ok) throw 0;
      setMode(true);
      const hj = await h.json();
      if (hj.llm) $('#disclosure span').textContent = `Questions are read by ${hj.llm}, running on this computer. Every number is measured from Sentinel-2 pixels and checked before it’s shown.`;
      try { EXAMPLES.splice(0, EXAMPLES.length, ...(await (await fetch('/api/examples')).json())); if (!log.querySelector('.msg-user')) renderEmpty(); } catch { /* keep defaults */ }
      const ps = await (await fetch('/api/places')).json();
      places = Object.fromEntries(ps.filter(p => p.name !== 'singapore').map(p => [p.name, p.bbox]));
      map.getSource('areas')?.setData(areasGeoJSON());
    } catch { setMode(false); }
  })();
  renderEmpty();

  // ---------- keyboard + toast ----------
  document.addEventListener('keydown', e => {
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName);
    if (e.key === '/' && !typing) { e.preventDefault(); q.focus(); }
    if (e.key === 'Escape' && !lp.hidden) { setLayers(false); lb.focus(); }
    if (e.key === 'Escape' && drawing) { setDrawing(false); $('#btn-draw').focus(); }
  });
  let tt;
  function toast(msg) { const t = $('#toast'); t.textContent = msg; t.hidden = false; clearTimeout(tt); tt = setTimeout(() => t.hidden = true, 3200); }
})();
