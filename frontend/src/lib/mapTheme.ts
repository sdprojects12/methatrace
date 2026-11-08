import type { Theme } from "../components/ThemeProvider";

/**
 * Both maps use CARTO's keyless vector styles. The public raster endpoints
 * (`dark_all`, `light_all`) now return an "API KEY REQUIRED" watermark, while
 * the vector styles remain keyless and keep the OSM + CARTO attribution.
 */
export const MAP_STYLE_URLS: Record<Theme, string> = {
  dark: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
  light: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
};

function readColor(variable: string, fallback: string) {
  if (typeof document === "undefined") return fallback;

  const value = getComputedStyle(document.documentElement)
    .getPropertyValue(variable)
    .trim();

  return value || fallback;
}

export interface PipelineMapPalette {
  active: string;
  maintenance: string;
  leaking: string;
  unknown: string;
  casing: string;
  hover: string;
  selected: string;
}

export function getPipelineMapPalette(): PipelineMapPalette {
  return {
    active: readColor("--pipeline-active", "#00e5a0"),
    maintenance: readColor("--pipeline-maintenance", "#ffb020"),
    leaking: readColor("--pipeline-leaking", "#ff4d5e"),
    unknown: readColor("--pipeline-unknown", "#64748b"),
    casing: readColor("--pipeline-casing", "#05080b"),
    hover: readColor("--pipeline-hover", "#f8fafc"),
    selected: readColor("--pipeline-selected", "#f8fafc"),
  };
}

export interface ObservationMapPalette {
  normal: string;
  threshold: string;
  mlFill: string;
  mlRing: string;
  both: string;
  stroke: string;
  selected: string;
  selectedStroke: string;
  halo: string;
  clusterFill: string;
  clusterStroke: string;
}

export function getObservationMapPalette(): ObservationMapPalette {
  return {
    normal: readColor("--obs-normal", "#00e5a0"),
    threshold: readColor("--obs-threshold", "#ffb020"),
    mlFill: readColor("--obs-ml-fill", "#38bdf8"),
    mlRing: readColor("--obs-ml-ring", "#e0f2fe"),
    both: readColor("--obs-both", "#ff4d5e"),
    stroke: readColor("--obs-stroke", "#0b0f14"),
    selected: readColor("--obs-selected", "#f8fafc"),
    selectedStroke: readColor("--obs-selected-stroke", "#0b0f14"),
    halo: readColor("--obs-halo", "#f8fafc"),
    clusterFill: readColor("--obs-cluster-fill", "#334155"),
    clusterStroke: readColor("--obs-cluster-stroke", "#94a3b8"),
  };
}
