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
    chevron: '<path d="m9 6 6 6-6 6"/>',
    'chev-down': '<path d="m6 9 6 6 6-6"/>',
    gear: '<path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2.2"/><circle cx="10" cy="17" r="2.2"/>',
    wand: '<path d="m4 20 11-11M14 4l1 2 2 1-2 1-1 2-1-2-2-1 2-1 1-2ZM19 11l.6 1.2 1.2.6-1.2.6L19 14.6l-.6-1.2-1.2-.6 1.2-.6L19 11Z"/>',
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
    copy: '<rect x="8" y="8" width="12" height="12" rx="2.5"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
    leaf: '<path d="M5 19c0-8 5-13 14-14-1 9-6 14-14 14Z"/><path d="M5 19 13 11"/>',
    ship: '<path d="M4 15h16l-2.5 4.5h-11L4 15Z"/><path d="M7 15V9h10v6M12 9V4M9 6.5h6"/>',
    mountain: '<path d="m3 19 6.5-11 4 6.5 2.5-3.5L21 19H3Z"/>',
    eye: '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z"/><circle cx="12" cy="12" r="3"/>',
    sharpen: '<rect x="4" y="4" width="16" height="16" rx="2.5"/><path d="M4 12h16M12 4v16M8 4v16M16 4v16M4 8h16M4 16h16" opacity=".45"/>',
    photo: '<rect x="3" y="5" width="18" height="14" rx="2.5"/><circle cx="9" cy="10" r="1.8"/><path d="m4 17 5-4.5 3.5 3 3-2.5L20 17"/>',
    ruler: '<path d="m3.5 15.5 12-12 5 5-12 12-5-5Z"/><path d="m7 12 2 2M10 9l2 2M13 6l2 2"/>',
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
  const START = { center: [10, 25], zoom: 1.8 };  // a neutral world view; nothing is region-specific
  const FALLBACK_PLACES = {
    tengah: [103.715, 1.345, 103.755, 1.375], tuas: [103.6, 1.22, 103.68, 1.34],
    'pulau tekong': [103.95, 1.38, 104.06, 1.43], 'jurong island': [103.66, 1.24, 103.73, 1.3],
    punggol: [103.89, 1.39, 103.93, 1.42], 'changi airport': [103.97, 1.33, 104.01, 1.4],
    'marina bay': [103.85, 1.27, 103.87, 1.3], 'central catchment': [103.78, 1.34, 103.83, 1.4],
  };
  const EXAMPLES = [
    'What changed at the Tesla Gigafactory Berlin since 2019?',
    'How much vegetation did the Tesla Gigafactory Berlin lose since 2019?',
    'How busy is the Bay of Gibraltar with ships since August 2026?',
    'How steep is the terrain around Zermatt?',
  ];
  // Same entries as /api/tools (src/geoask/agent/catalog.py); used when there's no server.
  let TOOLS = [
    { id: 'embedding_change', title: 'Any change', icon: 'sparkle', summary: 'The Clay foundation model compares every 80 m patch between two dates, so it finds construction, clearing or new water without choosing an index.', example: 'What changed at the Tesla Gigafactory Berlin since 2019?', available: true },
    { id: 'index_change', title: 'Vegetation, water, built-up', icon: 'leaf', summary: 'Spectral indices (NDVI, MNDWI, NDBI) measured in hectares lost and gained.', example: 'How much vegetation did the Tesla Gigafactory Berlin lose since 2019?', available: true },
    { id: 'activity', title: 'Vessel activity', icon: 'ship', summary: 'Vessels on every Sentinel-1 radar pass (day, night, through cloud), unusual days flagged, with a density map.', example: 'How busy is the Bay of Gibraltar with ships since August 2026?', available: true },
    { id: 'terrain', title: 'Terrain', icon: 'mountain', summary: 'Elevation, slope and relief from the Copernicus 30 m elevation model.', example: 'How steep is the terrain around Zermatt?', available: true },
    { id: 'viewshed', title: 'Viewshed', icon: 'eye', summary: 'What can be seen from a point, allowing for Earth curvature. Right-click the map for a point, or measure two points for line of sight.', example: 'What can a 2 m observer at 45.98365, 7.78474 see within 10 km?', available: true },
    { id: 'super_resolve', title: 'Sharpened view', icon: 'sharpen', summary: 'Sentinel-2 sharpened from 10 m to 2.5 m (SEN2SR) for viewing, with a consistency map. Never used for measurement.', example: 'Show me a sharper image of the Sydney Opera House', available: true },
  ];
  let live = false, places = FALLBACK_PLACES, active = null, busy = false, selection = null;

  // ---------- map ----------
  const eox = y => `https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-${y}_3857/default/g/{z}/{y}/{x}.jpg`;
  const S2_ATTR = '<a href="https://s2maps.eu" target="_blank" rel="noopener">Sentinel-2 cloudless</a> by EOX (Copernicus Sentinel data)';
  const map = new maplibregl.Map({
    container: 'map',
    style: 'https://tiles.openfreemap.org/styles/fiord',
    center: START.center, zoom: START.zoom,
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
    map.addLayer({ id: 'areas-fill', type: 'fill', source: 'areas', layout: { visibility: 'none' }, paint: { 'fill-color': '#5aa9ff', 'fill-opacity': 0.04 } });
    map.addLayer({ id: 'areas-line', type: 'line', source: 'areas', layout: { visibility: 'none' },
      paint: { 'line-color': '#8cc2ff', 'line-width': 1.2, 'line-dasharray': [3, 2], 'line-opacity': 0.75 } });
    map.addLayer({ id: 'areas-label', type: 'symbol', source: 'areas', minzoom: 10.5,
      layout: { visibility: 'none', 'text-field': ['get', 'title'], 'text-size': 12, 'text-font': ['Noto Sans Regular'], 'text-anchor': 'top-left', 'text-offset': [0.4, 0.4] },
      paint: { 'text-color': '#cfe3ff', 'text-halo-color': '#070b12', 'text-halo-width': 1.4 } });
    map.addSource('sel', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
    map.addLayer({ id: 'sel-fill', type: 'fill', source: 'sel', paint: { 'fill-color': '#5aa9ff', 'fill-opacity': 0.12 } });
    map.addLayer({ id: 'sel-line', type: 'line', source: 'sel', paint: { 'line-color': '#8cc2ff', 'line-width': 2 } });
    map.on('click', 'areas-fill', e => { if (!drawing && !measuring) focusPlace(e.features[0].properties.name); });
    map.on('mouseenter', 'areas-fill', () => map.getCanvas().style.cursor = 'pointer');
    map.on('mouseleave', 'areas-fill', () => map.getCanvas().style.cursor = '');

  });
  map.on('error', e => { if (String(e?.error?.message || '').includes('styles/fiord')) toast('Map style unavailable — check your connection.'); });

  // ---------- coordinates: decimal, DMS, MGRS or UTM (click the readout to switch) ----------
  const FORMATS = ['dd', 'dms', 'mgrs', 'utm'], FORMAT_NAMES = { dd: 'Decimal', dms: 'DMS', mgrs: 'MGRS', utm: 'UTM' };
  let fmt = 'dd';
  try { fmt = FORMATS.includes(localStorage.getItem('geoask.fmt')) ? localStorage.getItem('geoask.fmt') : 'dd'; } catch { /* private mode */ }
  let lastPos = { lng: START.center[0], lat: START.center[1] };
  const hud = $('#hud');
  const showHud = () => { hud.textContent = Geo.format(lastPos.lng, lastPos.lat, fmt); };
  hud.onclick = () => {
    fmt = FORMATS[(FORMATS.indexOf(fmt) + 1) % FORMATS.length];
    try { localStorage.setItem('geoask.fmt', fmt); } catch { /* ignore */ }
    showHud(); toast(`Coordinates: ${FORMAT_NAMES[fmt]}`);
  };
  map.on('mousemove', e => { lastPos = e.lngLat; showHud(); });
  map.on('move', () => { if (matchMedia('(hover: none)').matches) { lastPos = map.getCenter(); showHud(); } });
  showHud();

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
  $('#btn-home').onclick = () => map.flyTo({ ...START, bearing: 0, pitch: 0, duration: reduceMotion ? 0 : 1200 });
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
      : { top: 80, bottom: 110, left: collapsed ? 60 : panel.offsetWidth + 50, right: 80 };
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
    $('#quick').hidden = !selection;
    if (selection && pendingArea) { const j = pendingArea; pendingArea = null; runDirect(j); }
    if (selection) {
      $('#sel-text').textContent = `Selected area · ${bboxKm2(selection).toFixed(1)} km²`;
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
  // Quick actions for a drawn area: one tap asks the question about the selection.
  const QUICK = [
    ['sparkle', 'Any change', 'What has changed here since 2019?'],
    ['leaf', 'Vegetation', 'How much vegetation was lost here since 2019?'],
    ['ship', 'Vessels', 'How busy is this area with ships over the last year?'],
    ['mountain', 'Terrain', 'How steep is the terrain here?'],
    ['sharpen', 'Sharpen', 'Show me a sharper image of this area'],
  ];
  $('#quick').innerHTML = QUICK.map(([ic, label, q]) => `<button class="qa" type="button" data-q="${esc(q)}">${icon(ic, 'icon sm')}${esc(label)}</button>`).join('');
  $('#quick').querySelectorAll('.qa').forEach(b => b.onclick = () => { if (!busy) ask(b.dataset.q); });
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


  // ---------- mapping: MGRS grid, hillshade, 3D buildings ----------
  map.on('style.load', () => {
    const before = labelLayers[0];
    map.addLayer({ id: 'hillshade', type: 'hillshade', source: 'dem', layout: { visibility: 'none' },
      paint: { 'hillshade-exaggeration': 0.55, 'hillshade-shadow-color': '#04070c', 'hillshade-highlight-color': '#9fc6ff' } }, before);
    if (map.getSource('openmaptiles')) {
      map.addLayer({ id: 'buildings-3d', type: 'fill-extrusion', source: 'openmaptiles', 'source-layer': 'building', minzoom: 14,
        layout: { visibility: 'none' },
        paint: { 'fill-extrusion-color': '#8fb3e0', 'fill-extrusion-opacity': 0.82,
          'fill-extrusion-height': ['coalesce', ['get', 'render_height'], 6],
          'fill-extrusion-base': ['coalesce', ['get', 'render_min_height'], 0] } });
    }
    map.addSource('mgrs', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
    map.addLayer({ id: 'mgrs-line', type: 'line', source: 'mgrs', filter: ['==', ['geometry-type'], 'LineString'], layout: { visibility: 'none' },
      paint: { 'line-color': ['match', ['get', 'kind'], 'gzd', '#ffd27a', '100k', '#8cc2ff', '#8cc2ff'],
        'line-width': ['match', ['get', 'kind'], 'gzd', 1.8, '100k', 1.4, 1],
        'line-opacity': ['match', ['get', 'kind'], 'gzd', 0.95, '100k', 0.85, 0.7] } });
    map.addLayer({ id: 'mgrs-label', type: 'symbol', source: 'mgrs', filter: ['==', ['geometry-type'], 'Point'], layout: { visibility: 'none',
      'text-field': ['get', 'label'], 'text-size': ['match', ['get', 'kind'], 'gzd', 14, 12], 'text-font': ['Noto Sans Regular'], 'text-allow-overlap': false },
      paint: { 'text-color': ['match', ['get', 'kind'], 'gzd', '#ffd27a', '#cfe3ff'], 'text-halo-color': '#070b12', 'text-halo-width': 1.4 } });
    map.addSource('measure', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
    map.addLayer({ id: 'measure-line', type: 'line', source: 'measure', filter: ['==', ['geometry-type'], 'LineString'],
      paint: { 'line-color': '#ffd27a', 'line-width': 2.2, 'line-dasharray': [2, 1] } });
    map.addLayer({ id: 'measure-pt', type: 'circle', source: 'measure', filter: ['==', ['geometry-type'], 'Point'],
      paint: { 'circle-radius': 4.5, 'circle-color': '#070b12', 'circle-stroke-color': '#ffd27a', 'circle-stroke-width': 2 } });
    map.addSource('pin', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
    map.addLayer({ id: 'pin', type: 'circle', source: 'pin',
      paint: { 'circle-radius': 6, 'circle-color': '#5aa9ff', 'circle-stroke-color': '#e8eef6', 'circle-stroke-width': 2 } });
  });

  const vis = (id, on) => map.getLayer(id) && map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none');
  $('#ov-hillshade').onchange = e => vis('hillshade', e.target.checked);
  const buildingsOn = () => $('#ov-buildings').checked && $('#btn-globe').getAttribute('aria-pressed') === 'true';
  $('#ov-buildings').onchange = () => vis('buildings-3d', buildingsOn());
  $('#btn-globe').addEventListener('click', () => vis('buildings-3d', buildingsOn()));

  // MGRS grid: grid-zone boundaries always; then 100 km, 10 km or 1 km lines as you zoom in.
  // Lines are UTM eastings/northings traced through the inverse projection, so they curve
  // correctly and stop at zone edges.
  function mgrsFeatures() {
    const z = map.getZoom(), b = map.getBounds(), feats = [];
    const W = Math.max(b.getWest(), -180), E = Math.min(b.getEast(), 180);
    const S = Math.max(b.getSouth(), -80), N = Math.min(b.getNorth(), 84);
    if (W >= E || S >= N) return feats;
    const line = (coords, kind) => coords.length > 1 && feats.push({ type: 'Feature', properties: { kind }, geometry: { type: 'LineString', coordinates: coords } });
    const label = (lng, lat, text, kind) => feats.push({ type: 'Feature', properties: { kind, label: text }, geometry: { type: 'Point', coordinates: [lng, lat] } });
    // grid zone designators (6° x 8°; the Norway/Svalbard exceptions are drawn as the regular grid)
    for (let lon = Math.ceil((W + 180) / 6) * 6 - 180; lon <= E; lon += 6) line([[lon, S], [lon, N]], 'gzd');
    for (let lat = Math.ceil((S + 80) / 8) * 8 - 80; lat <= N; lat += 8) line([[W, lat], [E, lat]], 'gzd');
    if (z < 7) {
      for (let lon = Math.floor((W + 180) / 6) * 6 - 180; lon < E; lon += 6)
        for (let lat = Math.floor((S + 80) / 8) * 8 - 80; lat < N; lat += 8) {
          const cx = Math.min(Math.max(lon + 3, W), E), cy = Math.min(Math.max(lat + 4, S), N);
          if (z >= 3) label(cx, cy, `${Geo.zoneFor(lon + 3, lat + 4)}${Geo.bandFor(lat + 4)}`, 'gzd');
        }
      if (z < 5.5) return feats;
    }
    const step = z < 9 ? 100000 : z < 12 ? 10000 : 1000, kind = step === 100000 ? '100k' : 'fine';
    for (let zone = Geo.zoneFor(W + 1e-9, 0); zone <= Geo.zoneFor(E - 1e-9, 0); zone++) {
      const zw = Math.max(W, Geo.cm(zone) - 3), ze = Math.min(E, Geo.cm(zone) + 3);
      for (const [s, n, south] of [[S, Math.min(N, 0), true], [Math.max(S, 0), N, false]]) {
        if (s >= n) continue;
        const corners = [[zw, s], [ze, s], [zw, n], [ze, n], [Geo.cm(zone), s], [Geo.cm(zone), n]].map(([x, y]) => Geo.utmForward(x, y, zone, south));
        const e0 = Math.min(...corners.map(c => c.e)), e1 = Math.max(...corners.map(c => c.e));
        const n0 = Math.min(...corners.map(c => c.n)), n1 = Math.max(...corners.map(c => c.n));
        if ((e1 - e0) / step > 120 || (n1 - n0) / step > 120) continue;  // too dense to be useful
        const inside = ([x, y]) => x >= zw - 1e-9 && x <= ze + 1e-9 && y >= s - 1e-9 && y <= n + 1e-9;
        const trace = pts => { let run = []; for (const p of pts) { if (inside(p)) run.push(p); else { line(run, kind); run = []; } } line(run, kind); };
        const K = 24;
        for (let e = Math.ceil(e0 / step) * step; e <= e1; e += step)
          trace(Array.from({ length: K + 1 }, (_, i) => Geo.utmInverse(e, n0 + (n1 - n0) * i / K, zone, south)));
        for (let nn = Math.ceil(n0 / step) * step; nn <= n1; nn += step)
          trace(Array.from({ length: K + 1 }, (_, i) => Geo.utmInverse(e0 + (e1 - e0) * i / K, nn, zone, south)));
        if (step === 100000 || z < 13) {  // label each square: "VU" for 100 km, easting/northing km for finer lines
          for (let e = Math.floor(e0 / step) * step; e < e1; e += step)
            for (let nn = Math.floor(n0 / step) * step; nn < n1; nn += step) {
              const c = Geo.utmInverse(e + step / 2, nn + step / 2, zone, south);
              if (!inside(c)) continue;
              const id = Geo.square(zone, e + 1, nn + 1);
              const txt = step === 100000 ? id : `${id} ${Math.floor((e % 100000) / 10000)} ${Math.floor((nn % 100000) / 10000)}`;
              if (step !== 1000) label(c[0], c[1], txt, kind);
            }
        }
      }
    }
    return feats;
  }
  const refreshGrid = () => { if ($('#ov-mgrs').checked) map.getSource('mgrs')?.setData({ type: 'FeatureCollection', features: mgrsFeatures() }); };
  $('#ov-mgrs').onchange = e => { vis('mgrs-line', e.target.checked); vis('mgrs-label', e.target.checked); refreshGrid(); };
  map.on('moveend', refreshGrid);

  const setCollapsedSafe = c => setCollapsed(c);  // defined with the panel below; called later
  // ---------- measure distance and bearing (WGS84 ellipsoid, Vincenty) ----------
  let measuring = false, mpts = [];
  const mhint = $('#measure-hint'), mout = $('#measure-out');
  function renderMeasure() {
    const feats = mpts.map(p => ({ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: p } }));
    if (mpts.length > 1) feats.push({ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: mpts } });
    map.getSource('measure')?.setData({ type: 'FeatureCollection', features: feats });
    if (mpts.length < 2) { mout.textContent = mpts.length ? 'Add another point.' : 'Click the map to add points.'; return; }
    let total = 0, leg;
    for (let i = 1; i < mpts.length; i++) { leg = Geo.inverse(...mpts[i - 1], ...mpts[i]); total += leg.m; }
    const mils = Math.round(leg.bearing * 6400 / 360) % 6400;
    const brg = `${leg.bearing.toFixed(1).padStart(5, '0')}° true · ${mils} mil`;
    mout.textContent = mpts.length > 2 ? `${Geo.fmtDist(total)} total · last leg ${Geo.fmtDist(leg.m)}, ${brg}` : `${Geo.fmtDist(total)} · ${brg}`;
  }
  function setMeasuring(on) {
    measuring = on; mhint.hidden = !on; $('#btn-measure').setAttribute('aria-pressed', on);
    document.body.classList.toggle('measuring', on);
    if (on) { if (drawing) setDrawing(false); mpts = []; renderMeasure(); $('#measure-centre').focus(); }
    else { map.getSource('measure')?.setData({ type: 'FeatureCollection', features: [] }); }
  }
  $('#btn-measure').onclick = () => setMeasuring(!measuring);
  $('#measure-done').onclick = () => setMeasuring(false);
  $('#measure-undo').onclick = () => { mpts.pop(); renderMeasure(); };
  // Line of sight along the last leg (terrain + buildings + trees from the 30 m surface model).
  $('#measure-los').onclick = async () => {
    if (mpts.length < 2) return toast('Add two points first.');
    if (!live) return toast('Line of sight needs geoask serve (live mode).');
    const [a, b] = mpts.slice(-2);
    setCollapsedSafe(false); log.querySelector('.empty')?.remove();
    const bot = document.createElement('div'); bot.className = 'msg-bot'; log.appendChild(bot);
    bot.innerHTML = `<p class="method">Checking line of sight…</p>`;
    try {
      const r = await (await fetch(`/api/line-of-sight?lon1=${a[0]}&lat1=${a[1]}&lon2=${b[0]}&lat2=${b[1]}&h1=2&h2=2`)).json();
      if (r.detail) throw new Error(typeof r.detail === 'string' ? r.detail : 'invalid points');
      bot.innerHTML = ''; bot.appendChild(losCard(r));
    } catch (e) { bot.innerHTML = `<div class="card error" role="alert"><h3>Couldn't check line of sight</h3><p>${esc(e.message)}</p></div>`; }
    log.scrollTop = log.scrollHeight;
  };
  function losCard(r) {
    const W = 320, H = 110, prof = r.profile, xs = prof.map(p => p[0]), zs = prof.map(p => p[1]);
    const z0 = zs[0] + r.observer_h_m, z1 = zs[zs.length - 1] + r.target_h_m;
    const lo = Math.min(...zs, z0, z1), hi = Math.max(...zs, z0, z1), X = x => x / r.distance_m * W, Y = z => H - 16 - (z - lo) / Math.max(hi - lo, 1) * (H - 26);
    const ground = `M0,${H - 16} ` + prof.map(([x, z]) => `L${X(x).toFixed(1)},${Y(z).toFixed(1)}`).join(' ') + ` L${W},${H - 16} Z`;
    const ob = r.first_obstruction;
    const card = document.createElement('div'); card.className = 'card';
    card.innerHTML = `<h3>Line of sight · ${r.visible ? 'Clear' : 'Blocked'}</h3>
      <div class="when">${esc(Geo.toMGRS(...r.from, 4))} → ${esc(Geo.toMGRS(...r.to, 4))} · ${esc(r.source)}</div>
      <div class="stats"><div class="stat ${r.visible ? 'gain' : 'loss'}"><div class="v">${r.visible ? 'Visible' : 'Not visible'}</div><div class="k">${r.observer_h_m} m observer → ${r.target_h_m} m target</div></div>
        <div class="stat"><div class="v">${Geo.fmtDist(r.distance_m)}</div><div class="k">Distance</div></div>
        ${ob ? `<div class="stat"><div class="v">${Geo.fmtDist(ob.distance_m)}</div><div class="k">First obstruction (${ob.above_sightline_m.toFixed(0)} m above the sight line)</div></div>` : `<div class="stat"><div class="v">${r.min_clearance_m.toFixed(0)} m</div><div class="k">Smallest clearance</div></div>`}</div>
      <svg class="spark" viewBox="0 0 ${W} ${H}" role="img" aria-label="Elevation profile with the sight line"><path d="${ground}" fill="#2a3b55"/><line x1="0" y1="${Y(z0).toFixed(1)}" x2="${W}" y2="${Y(z1).toFixed(1)}" stroke="${r.visible ? '#34d1c4' : '#ff7a45'}" stroke-width="1.6" stroke-dasharray="4 3"/>${ob ? `<circle cx="${X(ob.distance_m).toFixed(1)}" cy="${Y(z0 + (z1 - z0) * ob.distance_m / r.distance_m + ob.above_sightline_m).toFixed(1)}" r="3.5" fill="#ff7a45"/>` : ''}<text x="0" y="${H - 2}" fill="#8193a8" font-size="10">0</text><text x="${W}" y="${H - 2}" fill="#8193a8" font-size="10" text-anchor="end">${Geo.fmtDist(r.distance_m)}</text></svg>
      <p class="method">From the 30 m surface model, with Earth curvature and refraction. Buildings and trees count as solid; anything smaller than 30 m is missed.</p>`;
    if (ob) map.getSource('pin')?.setData({ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: ob.lonlat } });
    return card;
  }
  $('#measure-centre').onclick = () => { const c = map.getCenter(); mpts.push([c.lng, c.lat]); renderMeasure(); };
  map.on('click', e => { if (measuring) { mpts.push([e.lngLat.lng, e.lngLat.lat]); renderMeasure(); } });

  // ---------- point card: right-click (or long-press) for every coordinate format + elevation ----------
  let popup;
  async function pointCard(lngLat, title = '') {
    const { lng, lat } = lngLat;
    const rows = FORMATS.map(f => `<div class="pc-row"><span>${FORMAT_NAMES[f]}</span><code>${esc(Geo.format(lng, lat, f))}</code><button class="btn-icon sm" type="button" data-copy="${esc(Geo.format(lng, lat, f))}" aria-label="Copy ${FORMAT_NAMES[f]}">${icon('copy', 'icon sm')}</button></div>`).join('');
    popup?.remove();
    popup = new maplibregl.Popup({ className: 'point-card', maxWidth: '360px' }).setLngLat(lngLat)
      .setHTML(`<div>${title ? `<div class="pc-title">${esc(title)}</div>` : ''}${rows}<div class="pc-row"><span>Elevation</span><code id="pc-elev">${live ? 'Looking up…' : 'Needs geoask serve'}</code></div>
        <div class="pc-actions"><button class="btn sm" type="button" data-act="view">${icon('eye', 'icon sm')}Viewshed From Here</button><button class="btn sm" type="button" data-act="measure">${icon('ruler', 'icon sm')}Measure From Here</button></div></div>`).addTo(map);
    const el = popup.getElement();
    el.querySelector('[data-act=view]').onclick = () => { popup.remove(); setCollapsedSafe(false); ask(`What can be seen from ${lat.toFixed(5)}, ${lng.toFixed(5)} within 3 km?`); };
    el.querySelector('[data-act=measure]').onclick = () => { popup.remove(); if (!measuring) setMeasuring(true); mpts = [[lng, lat]]; renderMeasure(); };
    popup.getElement().querySelectorAll('[data-copy]').forEach(b => b.onclick = async () => {
      try { await navigator.clipboard.writeText(b.dataset.copy); toast('Copied'); } catch { toast('Copy isn’t available here'); }
    });
    if (live) {
      try {
        const r = await (await fetch(`/api/elevation?lon=${lng}&lat=${lat}`)).json();
        const el = $('#pc-elev'); if (el) el.textContent = r.elevation_m != null ? `${r.elevation_m.toFixed(0)} m · ${r.source}` : 'No data here';
      } catch { const el = $('#pc-elev'); if (el) el.textContent = 'Unavailable'; }
    }
  }
  map.on('contextmenu', e => { e.preventDefault(); pointCard(e.lngLat); });

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
  // Bundled names as you type; the worldwide geocoder only on Enter (its usage policy forbids
  // search-as-you-type, and one lookup per Enter keeps us well inside its 1 request/s limit).
  let onlineTerm = null;
  async function renderResults(online = false) {
    const term = q.value.trim().toLowerCase();
    if (live) {
      const my = ++searchSeq;
      try {
        const rs = await (await fetch(`/api/search?q=${encodeURIComponent(term)}${online ? '&online=true' : ''}`)).json();
        if (my !== searchSeq) return;
        found = Object.fromEntries(rs.map(r => [r.name, r.bbox]));
        onlineTerm = online ? term : null;
      } catch { found = {}; }
    } else {
      found = Object.fromEntries(Object.entries(places).filter(([n]) => !term || n.includes(term)).slice(0, 8));
    }
    const pt = Geo.parseCoords(q.value);
    if (pt) found = { [`${COORD}${pt[0]},${pt[1]}`]: [pt[0] - 0.004, pt[1] - 0.004, pt[0] + 0.004, pt[1] + 0.004], ...found };
    items = Object.keys(found);
    const hint = live && term && !pt && onlineTerm !== term
      ? `<li role="option" aria-disabled="true" class="hint">Press Return to search the whole world</li>` : '';
    const label = n => n.startsWith(COORD) ? `Go to ${Geo.format(...n.slice(COORD.length).split(',').map(Number), fmt)}`
      : /,/.test(n) ? n : titleCase(n);  // geocoder names arrive already cased
    results.innerHTML = (items.map((n, i) => `<li role="option" id="opt-${i}" aria-selected="${i === sel}" data-name="${esc(n)}">${icon('pin', 'icon sm')}<span>${esc(label(n))}</span><span class="meta">${approxKm2(found[n])} km²</span></li>`).join('') + hint)
      || `<li role="option" aria-disabled="true">${live ? 'No match anywhere. Try another name, or draw an area.' : 'No match. Try another name, or draw an area.'}</li>`;
    results.hidden = false; search.setAttribute('aria-expanded', 'true');
    q.setAttribute('aria-activedescendant', sel >= 0 ? `opt-${sel}` : '');
  }
  const approxKm2 = b => { const a = bboxKm2(b); return a >= 100 ? a.toFixed(0) : a.toFixed(1); };
  const closeResults = () => { results.hidden = true; search.setAttribute('aria-expanded', 'false'); sel = -1; };
  q.addEventListener('focus', renderResults);
  q.addEventListener('input', () => { sel = -1; renderResults(); });
  q.addEventListener('keydown', e => {
    if (e.key === 'ArrowDown') { sel = Math.min(sel + 1, items.length - 1); renderResults(); e.preventDefault(); }
    else if (e.key === 'ArrowUp') { sel = Math.max(sel - 1, 0); renderResults(); e.preventDefault(); }
    else if (e.key === 'Enter') {
      e.preventDefault();
      if (live && sel < 0 && !Geo.parseCoords(q.value) && onlineTerm !== q.value.trim().toLowerCase()) { renderResults(true); return; }
      const n = items[Math.max(sel, 0)]; if (n) { focusPlace(n); closeResults(); q.blur(); }
    }
    else if (e.key === 'Escape') { closeResults(); q.blur(); }
  });
  results.addEventListener('pointerdown', e => { const li = e.target.closest('li[data-name]'); if (li) { e.preventDefault(); focusPlace(li.dataset.name); closeResults(); q.blur(); } });
  q.addEventListener('blur', () => setTimeout(closeResults, 120));

  const COORD = '@coord:';
  function focusPlace(name) {
    if (name.startsWith(COORD)) {  // a typed coordinate: fly there, drop a pin, open its point card
      const [lng, lat] = name.slice(COORD.length).split(',').map(Number);
      map.getSource('pin')?.setData({ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: [lng, lat] } });
      map.flyTo({ center: [lng, lat], zoom: Math.max(map.getZoom(), 14), duration: reduceMotion ? 0 : 1100 });
      map.once('moveend', () => pointCard({ lng, lat }));
      return;
    }
    const [w, s, e, n] = found[name] || places[name];
    const short = name.split(',')[0];
    q.value = /,/.test(name) ? short : titleCase(name);
    map.fitBounds([[w, s], [e, n]], { padding: pad(), duration: reduceMotion ? 0 : 1100, maxZoom: 15 });
    const ask = $('#ask');
    if (!ask.value.trim()) { ask.value = `How much vegetation did ${/,/.test(name) ? short : titleCase(name)} lose since 2019?`; ask.dispatchEvent(new Event('input')); }
  }

  // ---------- panel ----------
  const panel = $('#panel');
  // One toggle, always in the same place in the top bar (HIG › Sidebars: collapsible, and people
  // must be able to bring it back from where they hid it). Shortcut: \
  const panelBtn = $('#btn-panel');
  function setCollapsed(c) {
    panel.dataset.collapsed = c; document.body.classList.toggle('panel-collapsed', c);
    panelBtn.setAttribute('aria-expanded', !c);
    panelBtn.setAttribute('aria-label', c ? 'Show panel' : 'Hide panel'); panelBtn.title = `${c ? 'Show' : 'Hide'} panel (\\)`;
    if (!c) $('#ask').focus({ preventScroll: true });
  }
  panelBtn.onclick = () => setCollapsed(panel.dataset.collapsed !== 'true');

  // Resizable panel: drag the edge, or focus it and use ←/→. Double-click resets. Remembered.
  const resizer = $('#resizer');
  const PW = { min: 320, max: 760, def: 420 };
  function setPanelWidth(w, save = true) {
    w = Math.round(Math.min(Math.max(w, PW.min), Math.min(PW.max, innerWidth - 140)));
    document.documentElement.style.setProperty('--panel-w', `${w}px`);
    resizer.setAttribute('aria-valuenow', w);
    if (save) try { localStorage.setItem('geoask.panelW', w); } catch { /* ignore */ }
  }
  try { const w = +localStorage.getItem('geoask.panelW'); if (w) setPanelWidth(w, false); } catch { /* ignore */ }
  resizer.addEventListener('pointerdown', e => {
    e.preventDefault(); resizer.setPointerCapture(e.pointerId); document.body.classList.add('resizing');
    const left = panel.getBoundingClientRect().left;
    const move = ev => setPanelWidth(ev.clientX - left);
    const up = () => { resizer.removeEventListener('pointermove', move); document.body.classList.remove('resizing'); map.resize(); };
    resizer.addEventListener('pointermove', move); resizer.addEventListener('pointerup', up, { once: true });
  });
  resizer.addEventListener('keydown', e => {
    const w = +resizer.getAttribute('aria-valuenow');
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); setPanelWidth(w + (e.key === 'ArrowRight' ? 24 : -24)); }
  });
  resizer.addEventListener('dblclick', () => setPanelWidth(PW.def));

  let sessionId = null;
  $('#new-chat').onclick = () => {
    sessionId = null; clearResult(); clearLocMap(); clearAttachments(); log.innerHTML = ''; renderEmpty(); askBox.focus();
  };

  const log = $('#log');
  function renderEmpty() {
    const card = t => `<div class="tool${t.available ? '' : ' off'}">
        <div class="tool-h">${icon(t.icon, 'icon sm')}<b>${esc(t.title)}</b>${live ? '' : '<span class="badge">Replay</span>'}</div>
        <p>${esc(t.summary)}</p>
        ${t.available ? `<button class="chip" type="button" data-q="${esc(t.example)}">${esc(t.example)}</button>`
          : `<p class="install">Not installed. ${esc(t.install)}</p>`}</div>`;
    const noModel = live && modelInfo?.kind === 'none';
    log.innerHTML = `<div class="empty">
      <h2>What would you like to find out?</h2>
      <p>Ask about any place on Earth, a box you draw, or coordinates. Add a photo to find where it was taken, then add clues to narrow it down.</p>
      ${noModel ? `<div class="card connect"><h3>Connect a model</h3><p class="method">GeoAsk works with Claude, a local Ollama model or any OpenAI-compatible model. Without one, simple questions still work.</p><button class="btn primary" type="button" data-open-settings>Open Settings</button></div>` : ''}
      <div class="tool locate-card"><div class="tool-h">${icon('photo', 'icon sm')}<b>Where was this photo taken?</b>${live ? '' : '<span class="badge">Replay</span>'}</div>
        <p>The model reads signs, roads, plants, buildings, terrain and the sun, checks them against open map data and imagery, and answers with likely areas, never a pin.</p>
        <button class="chip" type="button" data-sample>Try a sample photo</button></div>
      <div class="tools">${TOOLS.map(card).join('')}</div>
      <p class="tip">Tips: draw a box ${icon('select', 'icon sm')} for quick actions, use the tools menu ${icon('wand', 'icon sm')} to run a tool directly, right-click the map for a point card.</p></div>`;
    log.querySelectorAll('.chip[data-q]').forEach(b => b.onclick = () => ask(b.dataset.q));
    log.querySelector('[data-sample]').onclick = trySample;
    log.querySelector('[data-open-settings]')?.addEventListener('click', openSettings);
  }

  // ---------- composer: text, photos (attach, drop, paste) ----------
  const askBox = $('#ask'), send = $('#send');
  const atts = [];  // {file, url}
  const canSend = () => !busy && (askBox.value.trim() || atts.length);
  askBox.addEventListener('input', () => {
    send.disabled = !canSend();
    askBox.style.height = 'auto'; askBox.style.height = Math.min(askBox.scrollHeight, 120) + 'px';
    askBox.classList.toggle('scroll', askBox.scrollHeight > 120);
  });
  askBox.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); $('#ask-form').requestSubmit(); } });
  $('#ask-form').addEventListener('submit', e => { e.preventDefault(); if (canSend()) ask(askBox.value.trim()); });
  function renderAtts() {
    $('#att').innerHTML = atts.map((a, i) => `<div class="thumb"><img src="${a.url}" alt="Photo ${i + 1}: ${esc(a.file.name)}"><button type="button" data-i="${i}" aria-label="Remove photo ${i + 1}">${icon('x', 'icon')}</button></div>`).join('');
    $('#att').querySelectorAll('button[data-i]').forEach(b => b.onclick = () => { const [a] = atts.splice(+b.dataset.i, 1); URL.revokeObjectURL(a.url); renderAtts(); });
    send.disabled = !canSend();
    askBox.placeholder = atts.length ? 'Add any clues you know' : 'Ask about a place or add a photo';
  }
  function addFiles(list) {
    const imgs = [...list].filter(f => f.type.startsWith('image/'));
    const room = 5 - atts.length;
    if (imgs.length > room) toast(room ? `Only ${room} more photo${room > 1 ? 's' : ''} can be added.` : 'Up to 5 photos per message.');
    imgs.slice(0, room).forEach(file => atts.push({ file, url: URL.createObjectURL(file) }));
    renderAtts(); askBox.focus();
  }
  function clearAttachments() { atts.splice(0).forEach(a => URL.revokeObjectURL(a.url)); renderAtts(); }
  const fileIn = $('#file');
  $('#attach').onclick = () => fileIn.click();
  fileIn.onchange = () => { addFiles(fileIn.files); fileIn.value = ''; };
  ['dragenter', 'dragover'].forEach(ev => panel.addEventListener(ev, e => { if (e.dataTransfer?.types?.includes('Files')) { e.preventDefault(); panel.classList.add('drop-over'); } }));
  ['dragleave', 'drop'].forEach(ev => panel.addEventListener(ev, e => { e.preventDefault(); panel.classList.remove('drop-over'); }));
  panel.addEventListener('drop', e => e.dataTransfer?.files?.length && addFiles(e.dataTransfer.files));
  document.addEventListener('paste', e => { if (e.clipboardData?.files?.length) addFiles(e.clipboardData.files); });
  async function trySample() {
    if (!live) return replayLocate();
    const blob = await (await fetch('../gallery/locate/photo.jpg')).blob();
    addFiles([new File([blob], 'sample-street.jpg', { type: 'image/jpeg' })]);
    askBox.value = 'Where was this photo taken?'; askBox.dispatchEvent(new Event('input'));
  }

  // ---------- asking: one chat, one model, every tool ----------
  let modelInfo = null, lastQuestion = '';
  function newTurn(question, photos = []) {
    log.querySelector('.empty')?.remove();
    const box = selection;
    const u = document.createElement('div'); u.className = 'msg-user';
    u.innerHTML = `${photos.length ? `<div class="u-photos">${photos.map(p => `<img src="${p.url}" alt="${esc(p.file.name)}">`).join('')}</div>` : ''}${esc(question)}${box ? `<small>${icon('select', 'icon sm')} selected area</small>` : ''}`;
    log.appendChild(u);
    const bot = document.createElement('div'); bot.className = 'msg-bot'; log.appendChild(bot);
    return { bot, steps: null, trace: null, question, box };
  }
  async function ask(question) {
    const photos = atts.slice();
    if (!question && photos.length) question = 'Where was this photo taken?';
    lastQuestion = question;
    busy = true; send.disabled = true;
    const ctx = newTurn(question, photos);
    askBox.value = ''; askBox.dispatchEvent(new Event('input'));
    atts.splice(0); renderAtts();  // the photos now belong to the message (object URLs kept for it)
    try {
      if (live) await askLive(question, photos, ctx);
      else if (photos.length) await replayLocate(ctx);
      else await askDemo(question, ctx);
    } catch (err) {
      showError(ctx, `Couldn't reach GeoAsk: ${err.message}`, 'Make sure geoask serve is still running, then try again.');
    } finally {
      busy = false; send.disabled = !canSend(); finishSteps(ctx);
      log.scrollTop = log.scrollHeight;
    }
  }
  async function streamInto(res, ctx) {
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
  async function askLive(question, photos, ctx) {
    const fd = new FormData();
    fd.append('message', question); fd.append('session', sessionId || '');
    if (ctx.box) fd.append('bbox', JSON.stringify(ctx.box));
    photos.forEach(p => fd.append('files', p.file, p.file.name));
    await streamInto(await fetch('/api/chat', { method: 'POST', body: fd }), ctx);
  }

  // Every event from the chat, the toolbar or a demo replay lands here.
  function handle(ev, ctx) {
    const fly = b => b && map.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: pad(), duration: reduceMotion ? 0 : 1100, maxZoom: 15 });
    switch (ev.type) {
      case 'session': sessionId = ev.id; break;
      case 'model': ctx.model = ev.label; break;
      case 'plan': {
        showPlan(ctx, ev);
        const pt = ev.args?.lon != null ? [ev.args.lon, ev.args.lat] : null;
        fly(ev.args?.bbox || places[ev.args?.place] || (pt && [pt[0] - 0.03, pt[1] - 0.03, pt[0] + 0.03, pt[1] + 0.03]));
        break;
      }
      case 'photos': { ensureTrace(ctx); const g = ev.photos.filter(p => p.meta?.gps).length; addStep(ctx, `Read ${ev.photos.length} photo${ev.photos.length > 1 ? 's' : ''} on this computer${g ? `: ${g} with camera GPS` : ''} (metadata stays here)`); break; }
      case 'recorded':
        map.getSource('loc-recorded')?.setData({ type: 'FeatureCollection', features: ev.points.map(p => ({ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: [p.lon, p.lat] } })) });
        ensureTrace(ctx);
        ctx.trace.insertAdjacentHTML('beforebegin', `<p class="lead">${icon('pin', 'icon sm')} Camera GPS: ${ev.points.map(p => esc(Geo.toMGRS(p.lon, p.lat, 4) || Geo.format(p.lon, p.lat, 'dd'))).join(', ')} <span class="method">(from the photo, not AI; amber dot)</span></p>`);
        break;
      case 'step': addStep(ctx, ev.text); if (ev.error) ctx.steps.lastElementChild?.classList.add('err'); break;
      case 'thinking': ensureTrace(ctx); ctx.steps.insertAdjacentHTML('beforeend', `<li class="think done">${esc(ev.text)}</li>`); break;
      case 'note': ensureTrace(ctx); finishSteps(ctx, true); ctx.steps.insertAdjacentHTML('beforeend', `<li class="note done">${esc(ev.text)}</li>`); ctx.trace.querySelector('.t-label').textContent = ev.text; break;
      case 'evidence':
        if (ev.kind === 'photos') { ensureTrace(ctx); ctx.steps.insertAdjacentHTML('beforeend', `<li class="ev done"><div class="evidence">${ev.items.map(p => `<figure><a href="${esc(p.page)}" target="_blank" rel="noopener"><img src="${esc(p.thumb)}" alt="Reference photo: ${esc(p.title)}" loading="lazy"></a><figcaption>${esc(p.source)} · ${esc(p.author)} · ${esc(p.licence)}</figcaption></figure>`).join('')}</div></li>`); }
        break;
      case 'usage': {
        const t = ev.tokens || {};
        ctx.costText = !ev.cost_usd ? '' : ev.cost_usd < 0.005 ? '< $0.01' : `≈ $${ev.cost_usd.toFixed(2)}`;
        ctx.tokens = `${(t.input_tokens || 0).toLocaleString()} tokens in, ${(t.output_tokens || 0).toLocaleString()} out`;
        ctx.model = ev.model || ctx.model;
        if (ctx.trace) traceCount(ctx);
        break;
      }
      case 'result': showResult(ctx, ev.result, ev.result.base); break;
      case 'estimate': showEstimate(ctx, ev.estimate); break;
      case 'clarify': showClarify(ctx, ev.message, ev.suggestions); fly(ev.bbox); break;
      case 'reply': showClarify(ctx, ev.message, ev.suggestions); break;
      case 'fly': fly(ev.bbox); break;
      case 'answer': showAnswer(ctx, ev.text, ev.source, ev.unverified || []); break;
      case 'error': showError(ctx, ev.message, ev.hint); break;
    }
    log.scrollTop = log.scrollHeight;
  }

  // Work trace, as in Claude's apps: one line that shows the current step while working, then
  // "Worked for 42 s · 7 steps". The chevron opens every step, the plan and the reasoning.
  function ensureTrace(ctx) {
    if (ctx.trace) return;
    ctx.t0 = performance.now();
    const d = document.createElement('details'); d.className = 'trace';
    d.innerHTML = `<summary><span class="t-ic"><span class="spinner" role="img" aria-label="Working"></span></span><span class="t-label">Working…</span><span class="t-n"></span>${icon('chevron', 'icon sm t-chev')}</summary><div class="t-body"><ul class="steps"></ul></div>`;
    ctx.bot.appendChild(d); ctx.trace = d; ctx.steps = d.querySelector('.steps');
  }
  function traceCount(ctx) {
    const n = ctx.steps.querySelectorAll('li:not(.note):not(.think):not(.ev)').length;
    ctx.trace.querySelector('.t-n').textContent = `${n} step${n === 1 ? '' : 's'}${ctx.costText ? ` · ${ctx.costText}` : ''}`;
  }
  function showPlan(ctx, p) {
    ensureTrace(ctx);
    const args = Object.entries(p.args).map(([k, v]) => `${k}=<b>${esc(v)}</b>`).join(', ');
    ctx.trace.insertAdjacentHTML('beforebegin', `<p class="lead">${esc(p.explanation)}</p>`);
    ctx.steps.insertAdjacentHTML('beforebegin', `<div class="plan" aria-label="Analysis plan">${esc(p.tool)}(${args})<br><span>planned by ${esc(p.planner)}</span></div>`);
  }
  function addStep(ctx, text) {
    ensureTrace(ctx);
    finishSteps(ctx, true);
    ctx.steps.insertAdjacentHTML('beforeend', `<li><span class="dot"><span class="spinner" role="img" aria-label="In progress"></span></span><span>${esc(text)}…</span></li>`);
    ctx.trace.querySelector('.t-label').textContent = `${text}…`;
    traceCount(ctx);
  }
  function finishSteps(ctx, intermediate = false) {
    if (!intermediate && ctx.trace && !ctx.traceDone) {
      ctx.traceDone = true;
      const sec = Math.max(1, Math.round((performance.now() - ctx.t0) / 1000));
      ctx.trace.querySelector('.t-ic').innerHTML = icon('check', 'icon sm');
      ctx.trace.querySelector('.t-label').textContent = `Worked for ${sec < 90 ? `${sec} s` : `${Math.round(sec / 60)} min`}`;
      traceCount(ctx);
    }
    ctx.steps?.querySelectorAll('li:not(.done)').forEach(li => { li.classList.add('done'); const d = li.querySelector('.dot'); if (d) d.innerHTML = icon('check', 'icon sm'); li.lastElementChild.textContent = li.lastElementChild.textContent.replace(/…$/, ''); });
  }
  // The model's reply. Numbers not found in any tool result or in what the user wrote are
  // highlighted, so a reader can tell a measurement from a model's guess.
  function showAnswer(ctx, text, source, unverified = []) {
    finishSteps(ctx);
    const bad = new Set(unverified);
    const fmt = t => esc(t)
      .replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')
      .replace(/(?<![\w.])-?\d[\d,]*(?:\.\d+)?/g, m => bad.has(m) ? `<mark class="unverified" title="Not found in any measurement">${m}</mark>` : m);
    const paras = String(text).split(/\n{2,}|\n(?=[-•] )/).map(p => `<p>${fmt(p.trim())}</p>`).join('');
    const by = /recorded/.test(source) ? 'Recorded answer from a live run' : /rule-based/.test(source) ? 'Fixed wording (no model)' : `Answer by ${source}`;
    const el = document.createElement('div'); el.className = 'answer';
    el.innerHTML = `${paras}<div class="src">${icon('sparkle', 'icon sm')}${esc(by)}${bad.size ? ` · <span class="warn">${bad.size} number${bad.size > 1 ? 's' : ''} not from a measurement (highlighted)</span>` : ''}</div>`;
    ctx.bot.appendChild(el);
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

  // Terrain and viewshed results: one overlay, no before/after.
  function showSingle(ctx, r, base) {
    finishSteps(ctx);
    const ha = n => fmtHa(n), m = v => `${Math.round(v).toLocaleString()} m`;
    const vs = r.tool === 'viewshed';
    const stats = vs ? [
      [ha(r.visible_ha), 'Visible ground', 'fm'], [`${Math.round(100 * r.visible_ha / r.area_ha)}%`, `Of the ${r.radius_m / 1000} km circle`],
      [m(r.observer_elev_m), 'Surface height at observer'], [`${r.observer_h_m} m → ${r.target_h_m} m`, 'Observer → target height']]
      : [[`${m(r.elev_min_m)} – ${m(r.elev_max_m)}`, 'Elevation range', 'fm'], [m(r.elev_mean_m), 'Mean elevation'],
        [`${r.slope_mean_deg.toFixed(1)}°`, 'Mean slope'], [ha(r.steep_ha), 'Steeper than 15°']];
    const title = vs ? `Viewshed · ${Geo.toMGRS(r.observer[0], r.observer[1], 4)}` : `Terrain · ${r.place_source === 'drawn' ? 'Selected area' : esc(/[A-Z0-9]/.test(r.place) ? r.place : titleCase(r.place))}`;
    const legend = vs ? `<span><i class="sw" style="background:#34d1c4"></i>Visible</span><span><i class="sw" style="background:#0b1220"></i>Hidden</span>`
      : `<span><i class="sw" style="background:linear-gradient(90deg,#16365c,#2878a0,#78aa78,#c8b482,#f5f5f5)"></i>Low → high, with hillshade</span>`;
    const method = vs
      ? `Sight lines are traced from the observer to every 30 m cell in the circle, allowing for Earth curvature and standard refraction. The ${esc(r.source)} is a surface model: buildings and tree canopy block views, but objects smaller than 30 m are missed.`
      : `Elevation and slope from the ${esc(r.source)} at 30 m. It's a surface model, so in towns and forests the heights are roof and canopy heights.`;
    const card = document.createElement('div'); card.className = 'card';
    card.innerHTML = `<h3>${title}</h3>
      <div class="when">${esc(r.source)} · ${r.grid.res_m} m · ${esc(r.grid.crs)}</div>
      <div class="stats">${stats.map(([v, k, c]) => `<div class="stat ${c || ''}"><div class="v">${esc(v)}</div><div class="k">${esc(k)}</div></div>`).join('')}</div>
      <div class="legend">${legend}</div>
      <div class="actions"><button class="btn primary act-show" type="button">${icon('target', 'icon sm')}Show on Map</button></div>
      <details><summary>Method</summary><p class="method">${method}</p></details>`;
    ctx.bot.appendChild(card);
    const show = () => {
      clearResult();
      map.addSource('res-delta', { type: 'image', url: base + r.images.overlay, coordinates: r.corners });
      map.addLayer({ id: 'res-delta', type: 'raster', source: 'res-delta', paint: { 'raster-fade-duration': 0, 'raster-opacity': 0.85 } }, map.getLayer('areas-fill') ? 'areas-fill' : undefined);
      const ov = $('#ov-change'); ov.disabled = false; ov.checked = true; $('#ov-change-d').textContent = vs ? 'Viewshed' : 'Terrain relief';
      if (vs) map.getSource('pin')?.setData({ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: r.observer } });
      const lons = r.corners.map(c => c[0]), lats = r.corners.map(c => c[1]);
      map.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]], { padding: pad(), duration: reduceMotion ? 0 : 1200 });
    };
    card.querySelector('.act-show').onclick = show;
    show();
  }

  // Super-resolution: the 10 m original and the 2.5 m estimate, blended with the timeline.
  function showSharpened(ctx, r, base) {
    finishSteps(ctx);
    const card = document.createElement('div'); card.className = 'card';
    card.innerHTML = `<h3>Sharpened view · ${r.place_source === 'drawn' ? 'Selected area' : esc(/[A-Z0-9]/.test(r.place) ? r.place : titleCase(r.place))}</h3>
      <div class="when">${esc(r.date)} · ${r.grid.res_m} m → ${r.out_res_m} m · ${esc(r.model)}</div>
      <p class="method"><b>For viewing only.</b> The extra detail is the model’s estimate. It’s constrained to agree with the real 10 m pixels, but GeoAsk never measures from it.</p>
      <div class="stats">
        <div class="stat fm"><div class="v">${r.out_res_m} m</div><div class="k">Display resolution</div></div>
        <div class="stat"><div class="v">${r.consistency_mean.toFixed(3)}</div><div class="k">Mean difference from real pixels (reflectance)</div></div></div>
      <div class="legend"><span><i class="sw" style="background:#ffc45c"></i>Least consistent with the 10 m image</span></div>
      <div class="actions">
        <button class="btn primary act-compare" type="button">${icon('compare', 'icon sm')}Compare 10 m / 2.5 m</button>
        <button class="btn act-show" type="button">${icon('target', 'icon sm')}Show Consistency</button></div>
      <details><summary>Model and source</summary><p class="method">${esc(r.citation)}. Licence ${esc(r.licence)}. Scenes: ${r.scenes.map(esc).join(', ')}.</p></details>`;
    ctx.bot.appendChild(card);
    const view = { ...r, index: 'sr', date0: '10 m original', date1: '2.5 m sharpened' };
    card.querySelector('.act-compare').onclick = () => showOnMap(view, base, true);
    card.querySelector('.act-show').onclick = () => showOnMap(view, base, false);
    showOnMap(view, base, true);
  }

  // Pattern of life: vessels per radar pass, unusual passes, and where they were.
  function showActivity(ctx, r, base) {
    finishSteps(ctx);
    const W = 320, H = 96, n = r.series.length, max = Math.max(...r.series.map(s => s.count), 1), bw = W / n;
    const unusual = new Set(r.unusual.map(u => u.date));
    const bars = r.series.map((s, i) => {
      const h = Math.max(2, (s.count / max) * (H - 18));
      const col = unusual.has(s.date) ? '#ffc45c' : '#5aa9ff';
      return `<rect x="${(i * bw + 1).toFixed(1)}" y="${(H - 14 - h).toFixed(1)}" width="${Math.max(bw - 2, 1).toFixed(1)}" height="${h.toFixed(1)}" rx="1.5" fill="${col}"><title>${s.date}: ${s.count} vessels${unusual.has(s.date) ? ' (unusual)' : ''}</title></rect>`;
    }).join('');
    const medY = H - 14 - (r.median_count / max) * (H - 18);
    const chart = `<svg class="spark" viewBox="0 0 ${W} ${H}" role="img" aria-label="Vessels per radar pass, ${r.date0} to ${r.date1}. Typical ${Math.round(r.median_count)}, busiest ${r.max_count} on ${r.max_date}.">${bars}
      <line x1="0" x2="${W}" y1="${medY.toFixed(1)}" y2="${medY.toFixed(1)}" stroke="#e8eef6" stroke-dasharray="3 3" stroke-width="1" opacity=".6"/>
      <text x="0" y="${H - 2}" fill="#8193a8" font-size="10">${esc(r.date0)}</text><text x="${W}" y="${H - 2}" fill="#8193a8" font-size="10" text-anchor="end">${esc(r.date1)}</text></svg>`;
    const card = document.createElement('div'); card.className = 'card';
    card.innerHTML = `<h3>Vessel activity · ${r.place_source === 'drawn' ? 'Selected area' : esc(/[A-Z0-9]/.test(r.place) ? r.place : titleCase(r.place))}</h3>
      <div class="when">${esc(r.date0)} → ${esc(r.date1)} · ${r.passes} radar passes · ${esc(r.sensor)}</div>
      <div class="stats">
        <div class="stat fm"><div class="v">${Math.round(r.median_count)}</div><div class="k">Vessels on a typical pass</div></div>
        <div class="stat"><div class="v">${r.max_count}</div><div class="k">Busiest · ${esc(r.max_date)}</div></div>
        <div class="stat"><div class="v">${r.unusual.length}</div><div class="k">Unusual passes</div></div>
        <div class="stat"><div class="v">${r.persistent_targets ?? r.fixed_targets ?? 0}</div><div class="k">Persistent targets set aside</div></div></div>
      ${chart}
      <div class="legend"><span><i class="sw" style="background:#5aa9ff"></i>Vessels per pass</span><span><i class="sw" style="background:#ffc45c"></i>Unusual for its orbit (beyond 3 robust SD)</span><span><i class="sw" style="background:#e8eef6;height:2px"></i>Typical</span></div>
      <div class="actions"><button class="btn primary act-show" type="button">${icon('target', 'icon sm')}Show on Map</button></div>
      <details><summary>Method and limits</summary><p class="method">Each pass is cut into 512 px slices with 20% overlap (SAHI-style), a CFAR detector finds radar-bright targets on open water, and boxes split by slice edges are merged. Targets in the same spot on 90% of passes (beacons, platforms, islets, or vessels laid up for months) are set aside from the counts. Each pass is judged against passes from the same orbit (${r.orbits ? r.orbits.length : 1} here), because each orbit sees the sea from its own side and time of day. Vessels under about 20–30 m are often missed, ships alongside piers merge with land, and nothing here says who a vessel is.</p></details>`;
    ctx.bot.appendChild(card);
    const show = async () => {
      clearResult();
      map.addSource('res-delta', { type: 'image', url: base + r.images.overlay, coordinates: r.corners });
      map.addLayer({ id: 'res-delta', type: 'raster', source: 'res-delta', paint: { 'raster-fade-duration': 0, 'raster-opacity': 0.8 } }, map.getLayer('areas-fill') ? 'areas-fill' : undefined);
      try {
        const pts = await (await fetch(base + r.images.points)).json();
        map.addSource('res-points', { type: 'geojson', data: pts });
        map.addLayer({ id: 'res-points', type: 'circle', source: 'res-points', paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 9, 2, 14, 5], 'circle-color': '#ffc45c', 'circle-stroke-color': '#070b12', 'circle-stroke-width': 1 } });
        if (!showActivity.bound) {  // register once; the layer is replaced on each result
          showActivity.bound = true;
          map.on('click', 'res-points', e => { const f = e.features[0]; pointCard(e.lngLat, `Vessel · ${f.properties.date} · ~${f.properties.length_m} m`); });
        }
      } catch { /* points are optional */ }
      const ov = $('#ov-change'); ov.disabled = false; ov.checked = true; $('#ov-change-d').textContent = 'Vessel density and detections';
      const lons = r.corners.map(c => c[0]), lats = r.corners.map(c => c[1]);
      map.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]], { padding: pad(), duration: reduceMotion ? 0 : 1200 });
    };
    card.querySelector('.act-show').onclick = show;
    show();
  }

  function showResult(ctx, r, base) {
    if (r.tool === 'enhance') return showEnhanced(ctx, r, base);
    if (r.tool === 'line_of_sight') { finishSteps(ctx); ctx.bot.appendChild(losCard(r)); return; }
    if (r.tool === 'activity') return showActivity(ctx, r, base);
    if (r.tool === 'terrain' || r.tool === 'viewshed') return showSingle(ctx, r, base);
    if (r.tool === 'super_resolve') return showSharpened(ctx, r, base);
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
    ['res-points', 'res-delta', 'res-after', 'res-before'].forEach(id => { if (map.getLayer(id)) map.removeLayer(id); if (map.getSource(id)) map.removeSource(id); });
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
    const ov = $('#ov-change'); ov.disabled = false; ov.checked = !compare; $('#ov-change-d').textContent = r.index === 'sr' ? 'Consistency with the 10 m image' : `${r.index.toUpperCase()} ${r.date0} → ${r.date1}`;
    $('#timeline').style.display = '';
    compareMode(r);
    if (compare) { tl.value = 0; updateCompare(); tl.focus(); toast('Drag the timeline to blend from before to after.'); }
    const lons = r.corners.map(c => c[0]), lats = r.corners.map(c => c[1]);
    map.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]], { padding: pad(), duration: reduceMotion ? 0 : 1200 });
  }


  // ---------- location estimates on the map ----------
  const circle = (lon, lat, km, n = 72) => {
    const pts = [];
    for (let i = 0; i <= n; i++) {
      const a = i / n * 2 * Math.PI;
      pts.push([lon + km / (111.32 * Math.cos(lat * Math.PI / 180)) * Math.sin(a), lat + km / 110.57 * Math.cos(a)]);
    }
    return pts;
  };
  map.on('style.load', () => {
    map.addSource('loc-areas', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
    map.addLayer({ id: 'loc-fill', type: 'fill', source: 'loc-areas', paint: { 'fill-color': ['case', ['==', ['get', 'rank'], 1], '#5aa9ff', '#f5b84a'], 'fill-opacity': ['case', ['==', ['get', 'rank'], 1], 0.18, 0.08] } });
    map.addLayer({ id: 'loc-line', type: 'line', source: 'loc-areas', paint: { 'line-color': ['case', ['==', ['get', 'rank'], 1], '#8cc2ff', '#f5b84a'], 'line-width': ['case', ['==', ['get', 'rank'], 1], 2.2, 1.4], 'line-dasharray': ['case', ['==', ['get', 'rank'], 1], ['literal', [1, 0]], ['literal', [3, 2]]] } });
    map.addSource('loc-labels', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
    map.addLayer({ id: 'loc-pt', type: 'circle', source: 'loc-labels', paint: { 'circle-radius': ['case', ['==', ['get', 'rank'], 1], 9, 7], 'circle-color': ['case', ['==', ['get', 'rank'], 1], '#1f6fe5', '#b07a17'], 'circle-stroke-color': '#e8eef6', 'circle-stroke-width': 1.5 } });
    map.addLayer({ id: 'loc-num', type: 'symbol', source: 'loc-labels', layout: { 'text-field': ['to-string', ['get', 'rank']], 'text-size': 11, 'text-font': ['Noto Sans Regular'], 'text-allow-overlap': true }, paint: { 'text-color': '#fff' } });
    map.addLayer({ id: 'loc-label', type: 'symbol', source: 'loc-labels', layout: { 'text-field': ['get', 'title'], 'text-size': 13, 'text-font': ['Noto Sans Regular'], 'text-offset': [0, 1.4], 'text-anchor': 'top' },
      paint: { 'text-color': '#e8eef6', 'text-halo-color': '#070b12', 'text-halo-width': 1.6 } });
    map.addSource('loc-recorded', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
    map.addLayer({ id: 'loc-recorded', type: 'circle', source: 'loc-recorded', paint: { 'circle-radius': 7, 'circle-color': '#f5b84a', 'circle-stroke-color': '#070b12', 'circle-stroke-width': 2 } });
  });
  function showAreas(areas) {
    map.getSource('loc-areas')?.setData({ type: 'FeatureCollection', features: areas.map((a, i) => ({ type: 'Feature', properties: { rank: i + 1 }, geometry: { type: 'Polygon', coordinates: [circle(a.lon, a.lat, a.radius_km)] } })) });
    map.getSource('loc-labels')?.setData({ type: 'FeatureCollection', features: areas.map((a, i) => ({ type: 'Feature', properties: { rank: i + 1, title: `${a.band} ${Math.round(a.confidence * 100)}%` }, geometry: { type: 'Point', coordinates: [a.lon, a.lat] } })) });
    fitAreas([areas[0]]);  // focus the most likely area; numbered markers show the others
  }
  function fitAreas(areas) {
    const pts = areas.flatMap(a => circle(a.lon, a.lat, a.radius_km * 1.6, 16));
    const lons = pts.map(p => p[0]), lats = pts.map(p => p[1]);
    map.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]], { padding: pad(), duration: reduceMotion ? 0 : 1200, maxZoom: 15 });
  }
  function clearLocMap() {
    ['loc-areas', 'loc-labels', 'loc-recorded'].forEach(id => map.getSource(id)?.setData({ type: 'FeatureCollection', features: [] }));
  }
  // Concise answer: headline, ranked areas (one line of why each), a few clue chips. Everything
  // else sits behind "Details". "Not here" and "Look again" continue the same conversation.
  function showEstimate(ctx, e) {
    finishSteps(ctx);
    showAreas(e.areas);
    const pct = c => `${Math.round(c * 100)}%`;
    const km = r => r < 1 ? `${Math.round(r * 1000)} m` : `${r < 10 ? r.toFixed(1) : Math.round(r)} km`;
    const rest = 1 - e.areas.reduce((s, a) => s + a.confidence, 0);
    const order = ['strong', 'medium', 'weak'];
    const clues = [...e.clues].sort((a, b) => order.indexOf(a.strength) - order.indexOf(b.strength));
    const card = document.createElement('div'); card.className = 'card loc-card';
    card.innerHTML = `<div class="kicker">${icon('pin', 'icon sm')}Location estimate</div><h3>${esc(e.summary)}</h3>
      ${e.country?.name ? `<div class="when">${esc(e.country.name)} · ${pct(e.country.confidence)}</div>` : ''}
      <ol class="areas">${e.areas.map((a, i) => `<li class="area" data-i="${i}">
        <button class="area-main" type="button" aria-label="Show area ${i + 1} on the map: ${esc(a.label)}, ${a.band} ${pct(a.confidence)}">
          <span class="rank">${i + 1}</span><span class="a-label">${esc(a.label)}</span><span class="band ${a.band}">${a.band} ${pct(a.confidence)}</span></button>
        <div class="meter" aria-hidden="true"><i style="width:${Math.max(2, a.confidence * 100)}%"></i></div>
        <p class="a-why">${esc(a.why)} <button class="link" type="button" data-not>Not here</button></p></li>`).join('')}</ol>
      <div class="clues" aria-label="Key clues">${clues.slice(0, 4).map(c => `<span class="clue ${c.strength}" title="${esc(c.kind)}: ${esc(c.text)} (${c.strength})">${esc(c.text)}</span>`).join('')}</div>
      <details class="more"><summary>Details</summary>
        <ul class="clue-list">${clues.map(c => `<li><b>${esc(c.kind)}</b> ${esc(c.text)} <span class="method">(${c.strength}${c.photo ? `, photo ${c.photo}` : ''})</span></li>`).join('')}</ul>
        ${e.areas.map((a, i) => `<p class="method">${i + 1}. within ${km(a.radius_km)} of ${esc(Geo.format(a.lon, a.lat, 'dd'))} (${esc(a.level)})</p>`).join('')}
        ${rest > 0.03 ? `<p class="method">Remaining ${pct(rest)}: somewhere else.</p>` : ''}
        ${e.caveats ? `<p class="method">${esc(e.caveats)}</p>` : ''}
        <p class="method">${esc(e.model)}${ctx.tokens ? ' · ' + esc(ctx.tokens) : ''}${e.cost_usd ? ` · ≈ $${e.cost_usd.toFixed(3)}` : ''}. AI estimate: confidence is the model’s own judgement and can be wrong.</p>
      </details>
      <p class="hint">Know more? Add a clue or another photo below to narrow it down.</p>
      <div class="actions"><button class="btn" type="button" data-again>${icon('retry', 'icon sm')}Look Again</button>
        <span class="feedback"><button class="btn-icon fb" aria-label="Right" aria-pressed="false">${icon('thumbup', 'icon sm')}</button><button class="btn-icon fb" aria-label="Wrong" aria-pressed="false">${icon('thumbdown', 'icon sm')}</button><span class="fb-note" role="status"></span></span></div>`;
    ctx.bot.appendChild(card);
    const follow = text => live ? ask(text) : toast('Follow-up clues need geoask serve with a model.');
    card.querySelectorAll('.area').forEach(li => {
      const a = e.areas[+li.dataset.i];
      li.querySelector('.area-main').onclick = () => { card.querySelectorAll('.area').forEach(x => x.classList.toggle('sel', x === li)); fitAreas([a]); };
      li.querySelector('[data-not]').onclick = () => follow(`It's not in ${a.label}. Reconsider.`);
    });
    card.querySelector('[data-again]').onclick = () => follow('Look at the photos again and reconsider your estimate.');
    card.querySelectorAll('.fb').forEach(b => b.onclick = () => { card.querySelectorAll('.fb').forEach(x => x.setAttribute('aria-pressed', x === b)); card.querySelector('.fb-note').textContent = 'Thanks'; });
  }

  // Generative enhancement: before/after with a draggable divider; always labelled as generated.
  function showEnhanced(ctx, r, base) {
    finishSteps(ctx);
    const card = document.createElement('div'); card.className = 'card';
    card.innerHTML = `<div class="kicker warn">${icon('sparkle', 'icon sm')}AI-generated detail · not evidence</div>
      <h3>Enhanced photo ${r.photo ? r.photo : ''}</h3>
      <div class="when">${esc(r.model)}${r.model.includes('×') ? '' : ` · ×${r.scale}`}${r.size ? ` · ${r.size[0]}×${r.size[1]} px` : ''}${r.guidance ? ` · “${esc(r.guidance)}”` : ''}</div>
      <div class="cmp" style="--x:50%"><img src="${base + r.images.after}" alt="Enhanced (generated)"><img class="top" src="${base + r.images.before}" alt="Original, upscaled"><span class="tag l">Original</span><span class="tag r">Generated</span>
        <input type="range" min="0" max="100" value="50" aria-label="Compare original and generated"></div>
      <div class="actions"><a class="btn" href="${base + r.images.after}" download>Download</a></div>
      <p class="method">The model invents plausible detail. Don’t treat text, faces or plates in it as real.</p>`;
    ctx.bot.appendChild(card);
    const cmp = card.querySelector('.cmp');
    cmp.querySelector('input').oninput = e => cmp.style.setProperty('--x', `${e.target.value}%`);
  }

  // ---------- Settings: model provider, keys, local models, offline models, privacy ----------
  const dlg = $('#settings'), sbody = $('#settings-body');
  function setModelChip(info) {
    modelInfo = info;
    $('#model-name').textContent = info ? info.label : 'Demo (recorded runs)';
    $('#model-chip').classList.toggle('off', !info || info.kind === 'none');
    $('#disclosure span').textContent = !info ? 'Demo: these answers are recorded runs. Run geoask serve to ask your own.'
      : info.kind === 'none' ? 'No model connected: simple questions use fixed rules. Connect a model in Settings for chat and photo geolocation.'
      : `${info.label} chooses the tools; every number is measured from satellite and elevation data and checked. Photos are sent without their metadata.`;
  }
  async function openSettings() {
    if (!live) { toast('Settings need geoask serve running on your computer.'); return; }
    dlg.showModal(); await renderSettings();
  }
  $('#btn-settings').onclick = openSettings;
  $('#model-chip').onclick = openSettings;
  $('#settings-close').onclick = () => dlg.close();
  dlg.addEventListener('click', e => { if (e.target === dlg) dlg.close(); });
  const post = (url, body, method = 'POST') => fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
  async function streamLines(res, onEv) {
    const reader = res.body.getReader(), dec = new TextDecoder(); let buf = '';
    for (;;) { const { value, done } = await reader.read(); if (done) break; buf += dec.decode(value, { stream: true });
      let i; while ((i = buf.indexOf('\n')) >= 0) { const l = buf.slice(0, i); buf = buf.slice(i + 1); if (l.trim()) onEv(JSON.parse(l)); } }
  }
  // Two-step download button: first click shows the size and asks to confirm (HIG › Responsibility).
  function confirmButton(btn, label, run) {
    btn.onclick = async () => {
      if (btn.dataset.armed !== '1') { btn.dataset.armed = '1'; btn.textContent = label; btn.classList.add('primary'); return; }
      btn.disabled = true; await run();
    };
  }
  async function renderSettings() {
    const st = await (await fetch('/api/settings')).json();
    const s = st.settings, act = st.active;
    const prov = s.provider === 'auto' ? act.kind : s.provider;
    const provs = [['anthropic', 'Claude API', 'Best results · needs an API key'], ['ollama', 'Ollama', 'Free · runs on this computer'],
      ['openai', 'OpenAI-compatible', 'LM Studio, llama.cpp, vLLM…'], ['none', 'No model', 'Fixed rules · offline']];
    sbody.innerHTML = `
      <section><h3>Model</h3>
        <p class="method">In use: <b>${esc(act.label)}</b>${act.kind !== 'none' && !act.vision ? ' · can’t see photos' : ''}${act.kind !== 'none' && !act.tools ? ' · can’t use tools' : ''}</p>
        <div class="prov" role="radiogroup" aria-label="Model provider">${provs.map(([id, t, d]) => `<button type="button" role="radio" aria-checked="${prov === id}" data-prov="${id}"><b>${t}</b><span>${d}</span></button>`).join('')}</div>
        <div id="prov-detail"></div></section>
      <section><h3>Privacy</h3>
        <label class="switch"><input type="checkbox" id="set-meta" ${s.share_photo_details ? 'checked' : ''}><span>Share photo details (camera GPS and time) with the model</span></label>
        <p class="method">Photos are always sent with their metadata removed. This switch sends the details as text, which can make locating much easier.</p></section>
      <section><h3>Offline models for tools</h3><ul class="offline">${st.offline.map(m => `<li>
        <div><b>${esc(m.title)}</b><span class="method">${m.size_mb ? (m.size_mb >= 1000 ? `${(m.size_mb / 1000).toFixed(1)} GB` : `${m.size_mb} MB`) : 'size checked on download'} · ${esc(m.licence)}</span></div>
        ${m.installed ? `<span class="ok">${icon('check', 'icon sm')}Installed</span>` : m.manual ? `<code>${esc(m.manual)}</code>` : `<button class="btn sm" type="button" data-fetch="${m.id}" data-size="${m.size_mb || ''}">Download</button>`}
        <p class="dl-msg method" data-msg="${m.id}"></p></li>`).join('')}</ul></section>`;
    sbody.querySelectorAll('[data-prov]').forEach(b => b.onclick = async () => { await post('/api/settings', { provider: b.dataset.prov }); await refreshModel(); renderSettings(); });
    sbody.querySelector('#set-meta').onchange = e => post('/api/settings', { share_photo_details: e.target.checked });
    sbody.querySelectorAll('[data-fetch]').forEach(btn => {
      const id = btn.dataset.fetch;
      confirmButton(btn, btn.dataset.size ? `Download ${+btn.dataset.size >= 1000 ? (btn.dataset.size / 1000).toFixed(1) + ' GB' : btn.dataset.size + ' MB'}?` : 'Check size and download?', async () => {
        const msg = sbody.querySelector(`[data-msg="${id}"]`);
        if (id === 'sd-x4-upscaler' && !btn.dataset.sized) {
          msg.textContent = 'Checking size…';
          const z = await (await fetch('/api/models/size?id=' + id)).json();
          btn.dataset.sized = '1'; btn.dataset.armed = '1'; btn.disabled = false; btn.textContent = `Download ${(z.size_mb / 1000).toFixed(1)} GB?`; msg.textContent = 'Needs the enhance extra: uv pip install -e ".[enhance]"'; return;
        }
        await streamLines(await post('/api/models/fetch', { id }), ev => { msg.textContent = ev.text || ev.message || (ev.type === 'done' ? 'Installed' : ''); });
        renderSettings();
      });
    });
    renderProvider(prov, st);
  }
  function renderProvider(prov, st) {
    const d = sbody.querySelector('#prov-detail'), s = st.settings;
    if (prov === 'anthropic') {
      const models = [['claude-sonnet-5-5', 'Claude Sonnet 5.5', 'balanced · ≈ $0.02–0.20 a question'], ['claude-opus-5-5', 'Claude Opus 5.5', 'most capable · about 2× Sonnet'], ['claude-haiku-5-5', 'Claude Haiku 5.5', 'fastest · cheapest']];
      d.innerHTML = `<div class="field"><label>API key</label>${st.keys.anthropic
        ? `<div class="row"><code>${esc(st.keys.anthropic)}</code> saved on this computer <button class="link" type="button" data-rm>Remove</button></div>`
        : `<form class="key-form" autocomplete="off"><input id="key-in" type="password" spellcheck="false" placeholder="Paste key: sk-ant-…" aria-label="Anthropic API key"><button class="btn primary" type="submit">Connect</button></form><p class="key-msg" role="status"></p><p class="method">Checked with Anthropic, saved only on this computer, never shown again. <a href="https://console.anthropic.com/settings/keys" target="_blank" rel="noopener">Get a key</a></p>`}</div>
        <div class="field"><label>Model</label><div class="opts">${models.map(([id, t, n]) => `<label class="opt"><input type="radio" name="cm" value="${id}" ${s.anthropic.model === id ? 'checked' : ''}><span>${t}<span class="d">${n}</span></span></label>`).join('')}</div></div>`;
      d.querySelectorAll('input[name=cm]').forEach(r => r.onchange = async () => { await post('/api/settings', { anthropic: { model: r.value } }); refreshModel(); });
      d.querySelector('[data-rm]')?.addEventListener('click', async () => { await post('/api/settings/key?provider=anthropic', null, 'DELETE'); await refreshModel(); renderSettings(); });
      const f = d.querySelector('.key-form');
      if (f) {
        const input = f.querySelector('input'), msg = d.querySelector('.key-msg');
        const go = async () => {
          msg.className = 'key-msg'; msg.textContent = 'Checking the key with Anthropic…';
          const r = await post('/api/settings/key', { provider: 'anthropic', key: input.value });
          const j = await r.json();
          if (!r.ok) { msg.className = 'key-msg err'; msg.textContent = j.detail; input.select(); return; }
          await refreshModel(); renderSettings(); toast(`Claude connected (${j.key}).`);
        };
        f.onsubmit = e => { e.preventDefault(); go(); };
        input.addEventListener('paste', () => setTimeout(() => /sk-ant-/.test(input.value) && go(), 0));  // paste = connect
        input.focus();
      }
    } else if (prov === 'ollama') {
      const o = st.ollama, cur = s.ollama.model || (st.active.kind === 'ollama' ? st.active.model : '');
      const have = new Set(o.models.map(m => m.name));
      d.innerHTML = `<div class="field"><label for="oh">Ollama address</label><div class="row"><input id="oh" class="text" value="${esc(s.ollama.host)}"><span class="${o.running ? 'ok' : 'warn'}">${o.running ? 'Running' : 'Not running'}</span></div>
        ${o.running ? '' : '<p class="method">Install Ollama from ollama.com and start it, then reopen Settings.</p>'}</div>
        ${o.models.length ? `<div class="field"><label>Installed models</label><div class="opts">${o.models.map(m => `<label class="opt"><input type="radio" name="om" value="${esc(m.name)}" ${cur === m.name ? 'checked' : ''}><span>${esc(m.name)}<span class="d">${m.size_gb} GB · ${m.capabilities.includes('vision') ? 'sees photos' : 'no vision'} · ${m.capabilities.includes('tools') ? 'uses tools' : 'no tools'}</span></span></label>`).join('')}</div></div>` : ''}
        ${o.running ? `<div class="field"><label>Download a model</label><ul class="offline">${st.recommended.filter(r => !have.has(r.name)).map(r => `<li><div><b>${esc(r.name)}</b><span class="method">${r.size_gb} GB · ${esc(r.note)}</span></div><button class="btn sm" type="button" data-pull="${esc(r.name)}">Download</button><p class="dl-msg method" data-pmsg="${esc(r.name)}"></p></li>`).join('')}</ul></div>` : ''}`;
      d.querySelector('#oh').onchange = async e => { await post('/api/settings', { ollama: { host: e.target.value } }); renderSettings(); };
      d.querySelectorAll('input[name=om]').forEach(r => r.onchange = async () => { await post('/api/settings', { provider: 'ollama', ollama: { model: r.value } }); refreshModel(); });
      d.querySelectorAll('[data-pull]').forEach(btn => {
        const r = st.recommended.find(x => x.name === btn.dataset.pull);
        confirmButton(btn, `Download ${r.size_gb} GB?`, async () => {
          const msg = d.querySelector(`[data-pmsg="${CSS.escape(r.name)}"]`);
          await streamLines(await post('/api/ollama/pull', { model: r.name }), ev => { msg.textContent = ev.text || ev.message || (ev.type === 'done' ? 'Installed' : ''); });
          await post('/api/settings', { provider: 'ollama', ollama: { model: r.name } }); await refreshModel(); renderSettings();
        });
      });
    } else if (prov === 'openai') {
      const o = s.openai;
      d.innerHTML = `<div class="field"><label for="ob">Server address</label><input id="ob" class="text" value="${esc(o.base_url)}" placeholder="http://localhost:1234/v1"></div>
        <div class="field"><label for="omn">Model name</label><input id="omn" class="text" value="${esc(o.model)}" placeholder="e.g. qwen2.5-vl-7b-instruct"></div>
        <label class="switch"><input type="checkbox" id="ov" ${o.vision ? 'checked' : ''}><span>This model can see images</span></label>
        <div class="field"><label for="ok">API key (if the server needs one)</label><div class="row">${st.keys.openai ? `<code>${esc(st.keys.openai)}</code> <button class="link" type="button" data-rmo>Remove</button>` : '<input id="ok" class="text" type="password" placeholder="optional">'}</div></div>
        <div class="actions"><button class="btn primary" type="button" id="osave">Save</button></div>
        <p class="method">For non-Claude models served with an OpenAI-style API (LM Studio, llama.cpp server, vLLM, OpenRouter…).</p>`;
      d.querySelector('#osave').onclick = async () => {
        await post('/api/settings', { provider: 'openai', openai: { base_url: d.querySelector('#ob').value, model: d.querySelector('#omn').value, vision: d.querySelector('#ov').checked } });
        const k = d.querySelector('#ok')?.value; if (k) await post('/api/settings/key', { provider: 'openai', key: k });
        await refreshModel(); renderSettings(); toast('Saved.');
      };
      d.querySelector('[data-rmo]')?.addEventListener('click', async () => { await post('/api/settings/key?provider=openai', null, 'DELETE'); renderSettings(); });
    } else {
      d.innerHTML = '<p class="method">Simple questions about change, vessels, terrain, viewshed and sharpening use fixed rules. Chat follow-ups and photo geolocation need a model.</p>';
    }
  }
  async function refreshModel() {
    try { const h = await (await fetch('/api/health')).json(); setModelChip(h.model); } catch { /* offline */ }
    if (!log.querySelector('.msg-user')) renderEmpty();
  }

  // ---------- tools menu: run one tool directly (no model) ----------
  const tpop = $('#tools-pop'), tbtn = $('#btn-tools');
  const setTools = open => { tpop.hidden = !open; tbtn.setAttribute('aria-expanded', open); tbtn.setAttribute('aria-pressed', open); if (open) tpop.querySelector('button')?.focus(); };
  tbtn.onclick = () => setTools(tpop.hidden);
  document.addEventListener('pointerdown', e => { if (!tpop.hidden && !tpop.contains(e.target) && !tbtn.contains(e.target)) setTools(false); });
  tpop.addEventListener('keydown', e => {
    const items = [...tpop.querySelectorAll('button')], i = items.indexOf(document.activeElement);
    if (e.key === 'ArrowDown') { e.preventDefault(); items[(i + 1) % items.length].focus(); }
    if (e.key === 'ArrowUp') { e.preventDefault(); items[(i - 1 + items.length) % items.length].focus(); }
    if (e.key === 'Escape') { setTools(false); tbtn.focus(); }
  });
  let pendingArea = null, pendingPoint = false;
  const TOOL_LABEL = { measure_change: t => t === 'any' ? 'Any change in the selected area' : 'Vegetation change in the selected area', vessel_activity: () => 'Vessel activity in the selected area', terrain: () => 'Terrain of the selected area', sharpen_image: () => 'Sharpen the selected area' };
  tpop.querySelectorAll('.tool-item').forEach(b => b.onclick = () => {
    setTools(false);
    const tool = b.dataset.tool, topic = b.dataset.topic;
    if (tool === 'los') { if (!measuring) setMeasuring(true); toast('Click two points, then Line of Sight.'); return; }
    if (!live) { toast('Tools run with geoask serve on your computer. This demo replays recorded runs.'); return; }
    if (tool === 'enhance') { startEnhance(); return; }
    if (tool === 'viewshed') { pendingPoint = true; document.body.classList.add('picking'); toast('Click the map to place the observer.'); return; }
    const job = { tool, args: topic ? { topic } : {}, label: TOOL_LABEL[tool](topic) };
    if (selection) runDirect(job); else { pendingArea = job; setDrawing(true); toast('Draw an area for this tool.'); }
  });
  map.on('click', e => {
    if (!pendingPoint) return;
    pendingPoint = false; document.body.classList.remove('picking');
    runDirect({ tool: 'viewshed', args: { lat: e.lngLat.lat, lon: e.lngLat.lng, radius_km: 5, observer_height_m: 2 }, label: `Viewshed from ${Geo.toMGRS(e.lngLat.lng, e.lngLat.lat, 4)}` });
  });
  async function runDirect(job) {
    setCollapsed(false);
    const ctx = newTurn(job.label); ctx.bot.previousElementSibling.classList.add('tool-msg');
    busy = true;
    try { await streamInto(await post('/api/run', { tool: job.tool, args: job.args, bbox: selection }), ctx); }
    catch (err) { showError(ctx, err.message, 'Check that geoask serve is running.'); }
    finally { busy = false; finishSteps(ctx); send.disabled = !canSend(); }
  }
  function startEnhance() {
    const go = async file => {
      setCollapsed(false);
      const guidance = askBox.value.trim();
      const ctx = newTurn(`Enhance photo${guidance ? `: “${guidance}”` : ''}`, [{ file, url: URL.createObjectURL(file) }]);
      ctx.bot.previousElementSibling.classList.add('tool-msg');
      askBox.value = ''; askBox.dispatchEvent(new Event('input'));
      const fd = new FormData(); fd.append('file', file, file.name); fd.append('guidance', guidance);
      try { await streamInto(await fetch('/api/enhance', { method: 'POST', body: fd }), ctx); }
      catch (err) { showError(ctx, err.message, 'Check that geoask serve is running.'); }
      finally { finishSteps(ctx); }
    };
    if (atts.length) { const a = atts.shift(); renderAtts(); go(a.file); return; }
    const once = () => { fileIn.removeEventListener('change', once, true); const f = fileIn.files[0]; fileIn.value = ''; if (f) go(f); };
    fileIn.addEventListener('change', once, { capture: true, once: true });
    toast('Choose a photo. Type a description first to guide the result.');
    fileIn.click();
  }

  // Demo mode: replay a recorded live geolocation run (scripts/record_locate.py), event by event.
  async function replayLocate(ctx) {
    const base = '../gallery/locate/';
    const run = await (await fetch(base + 'run.json')).json();
    if (!ctx) {
      const blob = await (await fetch(base + run.photo)).blob();
      ctx = newTurn('Where was this photo taken?', [{ file: new File([blob], 'sample-street.jpg'), url: base + run.photo }]);
    }
    ensureTrace(ctx);
    addStep(ctx, 'Read 1 photo on this computer (metadata stays here)');
    let last = 0;
    for (const ev of run.events) {
      await sleep(Math.min(1400, Math.max(250, (ev.t - last) * 120)));
      last = ev.t;
      ctx.t0 = performance.now() - ev.t * 1000;  // the trace shows the recorded run's timing
      handle(ev, ctx);
    }
    showAnswer(ctx, `Recorded run with ${run.model} on a photo by ${run.credit.replace(/^Photo: /, '')}. Run GeoAsk yourself to locate your own photos.`, 'recorded run');
  }

  // ---------- demo mode (GitHub Pages: no server) ----------
  const sleep = ms => new Promise(r => setTimeout(r, reduceMotion ? 0 : ms));
  // Demo replays for the tools that aren't change maps: each gallery entry stores the question,
  // the plan, the progress steps, the result and the answer from a real Live run.
  const DEMO_TOOL = [
    [/\b(ships?|vessels?|boats?|anchorage|maritime|pattern of life|activity|busy)\b/i, 'activity'],
    [/\b(viewshed|line of sight|visible from|can\b[^?]{0,60}\bsee|seen from|vantage)\b/i, 'viewshed'],
    [/\b(elevation|terrain|slope|steep|altitude|hill|mountain|relief)\b/i, 'terrain'],
    [/\b(sharpen|sharper|super[- ]?res\w*|enhance|high[- ]res\w*|higher[- ]res\w*|2\.5 ?m)\b/i, 'super_resolve'],
  ];
  async function askDemoTool(id, question, ctx) {
    const base = `../gallery/${id}/`;
    const r = await (await fetch(base + 'result.json')).json();
    const d = r.demo;
    if (d.question.toLowerCase() !== question.toLowerCase()) {
      ctx.bot.insertAdjacentHTML('beforeend', `<p>This demo can't run new analyses, because GitHub Pages has no server. Here is a recorded run of a similar question: <i>${esc(d.question)}</i></p>`);
    }
    handle({ type: 'plan', ...d.plan }, ctx);
    for (const s of d.steps) { addStep(ctx, s); log.scrollTop = log.scrollHeight; await sleep(380); }
    showResult(ctx, r, base);
    showAnswer(ctx, d.answer, 'template (recorded run)');
  }
  async function askDemo(question, ctx) {
    const tool = DEMO_TOOL.find(([re]) => re.test(question));
    if (tool) return askDemoTool(tool[1], question, ctx);
    // A topic word picks the vegetation example; an open "what changed" question picks Clay.
    const topic = /vegetat|forest|green|tree|park|water|coast|built|construct/i.test(question);
    return askDemoTool(topic ? 'index_change' : 'embedding_change', question, ctx);
  }

  // ---------- boot ----------
  function setMode(isLive) {
    live = isLive;
    document.body.classList.toggle('demo', !isLive);
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
      setModelChip((await h.json()).model);
      try { TOOLS = await (await fetch('/api/tools')).json(); } catch { /* keep the built-in list */ }
      if (!log.querySelector('.msg-user')) renderEmpty();
      const ps = await (await fetch('/api/places')).json();
      places = Object.fromEntries(ps.filter(p => p.name !== 'singapore').map(p => [p.name, p.bbox]));
      map.getSource('areas')?.setData(areasGeoJSON());
    } catch { setMode(false); setModelChip(null); }
  })();
  renderEmpty();

  // ---------- keyboard + toast ----------
  document.addEventListener('keydown', e => {
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName);
    if (e.key === '/' && !typing) { e.preventDefault(); q.focus(); }
    if (e.key === '\\' && !typing) { e.preventDefault(); panelBtn.click(); }
    if (e.key === 'Escape' && !lp.hidden) { setLayers(false); lb.focus(); }
    if (e.key === 'Escape' && pendingPoint) { pendingPoint = false; document.body.classList.remove('picking'); }
    if (e.key === ',' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); openSettings(); }
    if (e.key === 'Escape' && drawing) { setDrawing(false); $('#btn-draw').focus(); }
    if (e.key === 'Escape' && measuring) { setMeasuring(false); $('#btn-measure').focus(); }
  });
  let tt;
  function toast(msg) { const t = $('#toast'); t.textContent = msg; t.hidden = false; clearTimeout(tt); tt = setTimeout(() => t.hidden = true, 3200); }
})();
