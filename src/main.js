import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { Protocol } from 'pmtiles';
import { buildStyle } from './basemap-style.js';
import { initSourcesModal } from './attribution.js';

const protocol = new Protocol();
maplibregl.addProtocol('pmtiles', protocol.tile);

const DATA_BASE = `${import.meta.env.BASE_URL}data/`;
const PMTILES_URL = new URL(`${DATA_BASE}canada_sidewalks.pmtiles`, location.href).href;
const DEV_SAMPLE_URL = new URL(`${DATA_BASE}dev_sample.geojson`, location.href).href;

// zoom >= 4 so the sidewalk tiles (minzoom 4) are visible in the home view
const HOME = { center: [-93, 51.5], zoom: 4.1, pitch: 35, bearing: -5 };

async function pickDataSource() {
  // Dev servers answer missing paths with index.html, so verify the PMTiles
  // magic bytes rather than trusting the status code.
  try {
    const probe = await fetch(PMTILES_URL, { headers: { Range: 'bytes=0-6' } });
    if (probe.ok && (await probe.text()).startsWith('PMTiles')) {
      return { kind: 'pmtiles', url: PMTILES_URL };
    }
  } catch {
    /* fall through to dev sample */
  }
  console.warn('canada_sidewalks.pmtiles not found — falling back to dev sample GeoJSON');
  return { kind: 'geojson', url: DEV_SAMPLE_URL };
}

const dataSource = await pickDataSource();

const map = new maplibregl.Map({
  container: 'map',
  style: buildStyle(dataSource),
  ...HOME,
  hash: true,
  attributionControl: false,
});

map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'top-right');
map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-left');

// MapLibre re-adds 'maplibregl-compact-show' during load (resize event triggers
// _updateCompact). Force collapse until the user clicks ⓘ.
{
  const attribEl = document.querySelector('.maplibregl-ctrl-attrib');
  const summary = attribEl?.querySelector('summary');
  let userInteracted = false;
  const forceCollapse = () => {
    if (userInteracted) return;
    attribEl.classList.remove('maplibregl-compact-show');
    attribEl.setAttribute('open', '');
  };
  forceCollapse();
  const observer = new MutationObserver(() => {
    if (!userInteracted && attribEl.classList.contains('maplibregl-compact-show')) {
      forceCollapse();
    }
  });
  observer.observe(attribEl, { attributes: true, attributeFilter: ['class', 'open'] });
  summary?.addEventListener('click', () => {
    userInteracted = true;
    setTimeout(() => observer.disconnect(), 100);
  });
}

// --- Fly-to presets ---
const PLACES = [
  { name: 'Toronto', center: [-79.3832, 43.6532], zoom: 14.5, pitch: 60, bearing: -17 },
  { name: 'Montréal', center: [-73.5674, 45.5019], zoom: 14.5, pitch: 60, bearing: 15 },
  { name: 'Vancouver', center: [-123.1207, 49.2827], zoom: 14.5, pitch: 60, bearing: -20 },
  { name: 'Calgary', center: [-114.0719, 51.0447], zoom: 14.5, pitch: 58, bearing: 0 },
  { name: 'Edmonton', center: [-113.4938, 53.5461], zoom: 14.5, pitch: 58, bearing: 0 },
  { name: 'Ottawa', center: [-75.6972, 45.4215], zoom: 14.5, pitch: 58, bearing: -10 },
  { name: 'Winnipeg', center: [-97.1384, 49.8951], zoom: 14.5, pitch: 55, bearing: 0 },
  { name: 'Québec City', center: [-71.208, 46.8139], zoom: 14.5, pitch: 58, bearing: 20 },
  { name: 'Hamilton', center: [-79.8711, 43.2557], zoom: 14.5, pitch: 55, bearing: 0 },
  { name: 'Kitchener–Waterloo', center: [-80.4925, 43.4516], zoom: 14.3, pitch: 55, bearing: 0 },
  { name: 'Halifax', center: [-63.5752, 44.6488], zoom: 14.5, pitch: 55, bearing: 10 },
  { name: 'Victoria', center: [-123.3656, 48.4284], zoom: 14.5, pitch: 55, bearing: 0 },
  { name: 'Saskatoon', center: [-106.6702, 52.1332], zoom: 14.3, pitch: 55, bearing: 0 },
  { name: 'Regina', center: [-104.6189, 50.4452], zoom: 14.3, pitch: 55, bearing: 0 },
  { name: 'Moncton', center: [-64.7782, 46.0878], zoom: 14.5, pitch: 55, bearing: 0 },
  { name: "St. John's", center: [-52.7126, 47.5615], zoom: 14.3, pitch: 55, bearing: -15 },
  { name: '🍁 All Canada', ...HOME },
];

const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

// --- City chip marquee ---
const nav = document.getElementById('places');
const track = nav.querySelector('.marquee-track');
const [mainSet, cloneSet] = nav.querySelectorAll('.marquee-set');

function makeChip(p, isClone) {
  const btn = document.createElement('button');
  btn.textContent = p.name;
  if (isClone) btn.tabIndex = -1; // clone set is aria-hidden; keep it out of tab order too
  btn.addEventListener('click', () => {
    map.flyTo({
      center: p.center,
      zoom: p.zoom,
      pitch: p.pitch,
      bearing: p.bearing,
      duration: prefersReducedMotion ? 0 : 2500,
    });
  });
  return btn;
}

for (const p of PLACES) mainSet.appendChild(makeChip(p, false));
for (const p of PLACES) cloneSet.appendChild(makeChip(p, true));

if (prefersReducedMotion) {
  nav.classList.add('reduced-motion'); // static, scrollable strip; clones hidden in CSS
  document.getElementById('marquee-toggle').hidden = true;
} else {
  // ~3.5s per chip per loop reads as a calm ticker; count-based so it needs no layout measurement
  track.style.setProperty('--marquee-duration', `${PLACES.length * 3.5}s`);
}

const marqueeToggle = document.getElementById('marquee-toggle');
marqueeToggle.addEventListener('click', () => {
  const paused = nav.classList.toggle('paused');
  marqueeToggle.setAttribute('aria-pressed', String(paused));
  marqueeToggle.setAttribute('aria-label', paused ? 'Play city ticker' : 'Pause city ticker');
  marqueeToggle.textContent = paused ? '▶' : '⏸';
});

// --- Legend filters: provenance × infrastructure class ---
const PROV_FILTERS = [
  { input: 'filter-both', value: 'both' },
  { input: 'filter-statcan', value: 'statcan_only' },
  { input: 'filter-osm', value: 'osm_only' },
];
const CLS_FILTERS = [
  { input: 'filter-cls-sidewalk', values: ['sidewalk'] },
  { input: 'filter-cls-path', values: ['path'] },
  { input: 'filter-cls-crossing', values: ['crossing', 'steps', 'bridge'] },
  { input: 'filter-cls-other', values: ['pedestrian_street', 'footway_other', 'other'] },
];
const NETWORK_LAYERS = ['sidewalk-core', 'sidewalk-glow'];

function applyFilters() {
  if (!map.getLayer('sidewalk-core')) return;
  const provs = PROV_FILTERS.filter((f) => document.getElementById(f.input).checked).map(
    (f) => f.value,
  );
  const clss = CLS_FILTERS.filter((f) => document.getElementById(f.input).checked).flatMap(
    (f) => f.values,
  );
  const provMatch = provs.length
    ? ['match', ['get', 'provenance'], provs, true, false]
    : ['boolean', false];
  const clsMatch = clss.length
    ? ['match', ['get', 'cls'], clss, true, false]
    : ['boolean', false];
  const filter = ['all', provMatch, clsMatch];
  for (const layer of NETWORK_LAYERS) map.setFilter(layer, filter);
}

for (const { input } of [...PROV_FILTERS, ...CLS_FILTERS]) {
  document.getElementById(input).addEventListener('change', applyFilters);
}
map.on('load', applyFilters);

// --- Layer toggles ---
const LAYER_TOGGLES = [
  { input: 'toggle-buildings', layer: 'building-3d' },
  { input: 'toggle-satellite', layer: 'satellite' },
];
for (const { input, layer } of LAYER_TOGGLES) {
  const checkbox = document.getElementById(input);
  const apply = () => {
    if (!map.getLayer(layer)) return;
    map.setLayoutProperty(layer, 'visibility', checkbox.checked ? 'visible' : 'none');
  };
  checkbox.addEventListener('change', apply);
  map.on('load', apply);
}

// --- Hover info card ---
const PROVENANCE_LABEL = {
  both: { text: 'In both sources', color: '#D80621' },
  statcan_only: { text: 'StatCan only', color: '#1D63C8' },
  osm_only: { text: 'OSM only', color: '#E39B00' },
};
const CLS_LABEL = {
  sidewalk: 'Sidewalk',
  path: 'Path / trail',
  crossing: 'Crossing',
  steps: 'Steps',
  bridge: 'Bridge or underpass',
  pedestrian_street: 'Pedestrian street',
  footway_other: 'Footway',
  other: 'Other',
};

const info = document.getElementById('info');
const infoStreet = document.getElementById('info-street');
const infoStatus = document.getElementById('info-status');
const infoDetail = document.getElementById('info-detail');
const infoLoc = document.getElementById('info-loc');

map.on('mousemove', (e) => {
  const layers = NETWORK_LAYERS.filter((l) => map.getLayer(l));
  if (!layers.length) return;
  const features = map.queryRenderedFeatures(
    [
      [e.point.x - 4, e.point.y - 4],
      [e.point.x + 4, e.point.y + 4],
    ],
    { layers },
  );
  if (!features.length) {
    info.hidden = true;
    map.getCanvas().style.cursor = '';
    return;
  }
  const f = features[0].properties;
  const prov = PROVENANCE_LABEL[f.provenance] ?? { text: f.provenance ?? '—', color: '#9AA4AD' };
  infoStreet.textContent = f.street && f.street !== 'null' ? f.street : 'Unnamed';
  infoStatus.textContent = prov.text;
  infoStatus.style.color = prov.color;
  const detail = [CLS_LABEL[f.cls] ?? f.cls];
  if (f.width && Number(f.width) > 0) detail.push(`${Number(f.width).toFixed(1)} m`);
  if (f.material && f.material !== 'null') detail.push(f.material);
  infoDetail.textContent = detail.join(' · ');
  infoLoc.textContent = f.muni && f.muni !== 'null' ? `${f.muni}, ${f.prov ?? ''}` : '';
  info.hidden = false;
  info.style.left = `${e.point.x + 14}px`;
  info.style.top = `${e.point.y + 14}px`;
  map.getCanvas().style.cursor = 'crosshair';
});

map.on('mouseout', () => {
  info.hidden = true;
});

initSourcesModal();

map.on('error', (e) => console.warn('map error:', e.error?.message ?? e));

window.map = map; // debugging handle
