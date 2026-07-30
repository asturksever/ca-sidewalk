// "Maple red & winter white" light basemap over OpenFreeMap vector tiles
// (OpenMapTiles schema) + optional satellite + unified sidewalks layer.

const COLORS = {
  ground: '#F7F9FB', // snow white
  groundLow: '#EEF2F6',
  water: '#C6DBEA', // frozen-lake blue
  park: '#E9F0E9', // faint evergreen
  roadMinor: '#E3E8ED',
  roadMajor: '#D2DAE1',
  building: '#E7EBEF',
  buildingTop: '#CBD4DC',
  boundary: '#B9C5CF',
  label: '#2B2F33', // dark charcoal
  labelHalo: '#FFFFFF',
  provBoth: '#D80621', // maple red — present in both sources
  provStatcan: '#1D63C8', // official blue — StatCan only
  provOsm: '#E39B00', // amber — OSM only
};

const provenanceColor = [
  'match',
  ['get', 'provenance'],
  'both',
  COLORS.provBoth,
  'statcan_only',
  COLORS.provStatcan,
  'osm_only',
  COLORS.provOsm,
  '#9AA4AD',
];

/**
 * @param {{kind: 'pmtiles'|'geojson', url: string}} data unified-network source
 */
export function buildStyle(data) {
  const isVector = data.kind === 'pmtiles';
  const sidewalkSource = isVector
    ? {
        type: 'vector',
        url: `pmtiles://${data.url}`,
        attribution:
          'Pedestrian network: Statistics Canada CPND 2025 &amp; © OpenStreetMap contributors',
      }
    : {
        type: 'geojson',
        data: data.url,
        attribution:
          'Pedestrian network: Statistics Canada CPND 2025 &amp; © OpenStreetMap contributors',
      };
  const sourceLayer = isVector ? { 'source-layer': 'sidewalks' } : {};

  return {
    version: 8,
    name: 'Sidewalks of Canada — maple red & winter white',
    glyphs: 'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf',
    sky: {
      'sky-color': '#DCEAF5',
      'horizon-color': '#F2F6F9',
      'fog-color': '#F7F9FB',
      'sky-horizon-blend': 0.7,
      'horizon-fog-blend': 0.6,
      'fog-ground-blend': 0.9,
      'atmosphere-blend': ['interpolate', ['linear'], ['zoom'], 0, 1, 6, 1, 8, 0.15],
    },
    projection: { type: 'globe' },
    sources: {
      openfreemap: {
        type: 'vector',
        url: 'https://tiles.openfreemap.org/planet',
      },
      satellite: {
        type: 'raster',
        tiles: [
          'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        ],
        tileSize: 256,
        maxzoom: 19,
        attribution: 'Imagery: Esri, Maxar, Earthstar Geographics',
      },
      sidewalks: sidewalkSource,
    },
    layers: [
      { id: 'background', type: 'background', paint: { 'background-color': COLORS.ground } },
      {
        id: 'park',
        type: 'fill',
        source: 'openfreemap',
        'source-layer': 'park',
        paint: { 'fill-color': COLORS.park, 'fill-opacity': 0.9 },
      },
      {
        id: 'landuse-green',
        type: 'fill',
        source: 'openfreemap',
        'source-layer': 'landcover',
        filter: ['match', ['get', 'class'], ['wood', 'grass', 'forest'], true, false],
        paint: { 'fill-color': COLORS.park, 'fill-opacity': 0.6 },
      },
      {
        id: 'water',
        type: 'fill',
        source: 'openfreemap',
        'source-layer': 'water',
        paint: { 'fill-color': COLORS.water },
      },
      {
        id: 'waterway',
        type: 'line',
        source: 'openfreemap',
        'source-layer': 'waterway',
        paint: { 'line-color': COLORS.water, 'line-width': 1.2 },
      },
      // --- roads ---
      {
        id: 'road-minor',
        type: 'line',
        source: 'openfreemap',
        'source-layer': 'transportation',
        minzoom: 11,
        filter: ['match', ['get', 'class'], ['minor', 'service', 'track'], true, false],
        paint: {
          'line-color': COLORS.roadMinor,
          'line-width': ['interpolate', ['exponential', 1.5], ['zoom'], 11, 0.5, 14, 2, 18, 10],
        },
      },
      {
        id: 'road-major',
        type: 'line',
        source: 'openfreemap',
        'source-layer': 'transportation',
        minzoom: 5,
        filter: [
          'match',
          ['get', 'class'],
          ['motorway', 'trunk', 'primary', 'secondary', 'tertiary'],
          true,
          false,
        ],
        paint: {
          'line-color': COLORS.roadMajor,
          'line-width': ['interpolate', ['exponential', 1.5], ['zoom'], 5, 0.6, 10, 1.4, 14, 5, 18, 20],
        },
      },
      // --- admin boundaries ---
      {
        id: 'boundary-province',
        type: 'line',
        source: 'openfreemap',
        'source-layer': 'boundary',
        filter: ['all', ['<=', ['get', 'admin_level'], 4], ['!=', ['get', 'maritime'], 1]],
        paint: {
          'line-color': COLORS.boundary,
          'line-width': ['interpolate', ['linear'], ['zoom'], 3, 0.8, 8, 1.5],
          'line-dasharray': [3, 2],
          'line-opacity': 0.9,
        },
      },
      // --- satellite imagery (toggled from the UI) ---
      {
        id: 'satellite',
        type: 'raster',
        source: 'satellite',
        layout: { visibility: 'none' },
        paint: {
          'raster-brightness-max': 0.95,
          'raster-saturation': -0.2,
        },
      },
      // --- unified pedestrian network (the data!) ---
      {
        id: 'sidewalk-glow',
        type: 'line',
        source: 'sidewalks',
        ...sourceLayer,
        minzoom: 11,
        layout: { 'line-cap': 'round' },
        paint: {
          'line-color': provenanceColor,
          'line-width': ['interpolate', ['linear'], ['zoom'], 11, 3, 14, 7, 17, 13],
          'line-blur': ['interpolate', ['linear'], ['zoom'], 11, 3, 17, 8],
          'line-opacity': 0.18, // soft tint halo on the light basemap, not neon
        },
      },
      {
        id: 'sidewalk-core',
        type: 'line',
        source: 'sidewalks',
        ...sourceLayer,
        layout: { 'line-cap': 'round' },
        paint: {
          'line-color': provenanceColor,
          'line-width': [
            'interpolate',
            ['linear'],
            ['zoom'],
            4, 0.7,
            8, 0.9,
            11, 1.1,
            14, 1.9,
            17, 3.4,
          ],
          'line-opacity': ['interpolate', ['linear'], ['zoom'], 4, 0.85, 11, 1],
        },
      },
      // --- 3D buildings ---
      {
        id: 'building-3d',
        type: 'fill-extrusion',
        source: 'openfreemap',
        'source-layer': 'building',
        minzoom: 13.5,
        paint: {
          'fill-extrusion-color': [
            'interpolate',
            ['linear'],
            ['coalesce', ['get', 'render_height'], 5],
            0, COLORS.building,
            60, COLORS.buildingTop,
          ],
          'fill-extrusion-height': ['coalesce', ['get', 'render_height'], 5],
          'fill-extrusion-base': ['coalesce', ['get', 'render_min_height'], 0],
          'fill-extrusion-opacity': 0.9,
        },
      },
      // --- labels ---
      {
        id: 'place-city',
        type: 'symbol',
        source: 'openfreemap',
        'source-layer': 'place',
        filter: ['match', ['get', 'class'], ['city', 'town'], true, false],
        layout: {
          'text-field': ['get', 'name'],
          'text-font': ['Noto Sans Bold'],
          'text-size': ['interpolate', ['linear'], ['zoom'], 4, 11, 10, 16],
        },
        paint: {
          'text-color': COLORS.label,
          'text-halo-color': COLORS.labelHalo,
          'text-halo-width': 1.6,
        },
      },
      {
        id: 'place-suburb',
        type: 'symbol',
        source: 'openfreemap',
        'source-layer': 'place',
        minzoom: 11,
        filter: ['match', ['get', 'class'], ['suburb', 'neighbourhood', 'quarter'], true, false],
        layout: {
          'text-field': ['get', 'name'],
          'text-font': ['Noto Sans Regular'],
          'text-size': 12,
        },
        paint: {
          'text-color': COLORS.label,
          'text-halo-color': COLORS.labelHalo,
          'text-halo-width': 1.3,
          'text-opacity': 0.85,
        },
      },
    ],
  };
}

export { COLORS };
