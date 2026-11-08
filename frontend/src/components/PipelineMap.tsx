"use client";

import { useEffect, useRef, useState } from "react";
import { Map, NavigationControl, setWorkerUrl } from "maplibre-gl";
import { fetchAPI } from "../lib/api";
import { useReportDownload } from "../lib/useReportDownload";
import type { Feature, FeatureCollection, LineString } from "geojson";
import { getAppliedTheme, useTheme } from "./ThemeProvider";
import { MAP_STYLE_URLS, getPipelineMapPalette } from "../lib/mapTheme";

setWorkerUrl("/maplibre-gl-worker.mjs");

interface PipelineProperties {
  pipeline_id: string;
  type: string;
  status: string;
  material: string;
  pressure_bar: number;
  depth_m: number;
  installed: number;
}

type PipelineFeature = Feature<LineString, PipelineProperties>;
type PipelineGeoJSON = FeatureCollection<LineString, PipelineProperties>;

const MAP_BOUNDS: [[number, number], [number, number]] = [
  [73.771, 18.695],
  [73.84, 18.81],
];

function pipelineBounds(
  feature: PipelineFeature
): [[number, number], [number, number]] | null {
  let minLng = Infinity;
  let minLat = Infinity;
  let maxLng = -Infinity;
  let maxLat = -Infinity;

  for (const [lng, lat] of feature.geometry.coordinates) {
    if (!Number.isFinite(lng) || !Number.isFinite(lat)) continue;
    minLng = Math.min(minLng, lng);
    minLat = Math.min(minLat, lat);
    maxLng = Math.max(maxLng, lng);
    maxLat = Math.max(maxLat, lat);
  }

  if (!Number.isFinite(minLng) || !Number.isFinite(minLat)) return null;

  return [
    [minLng, minLat],
    [maxLng, maxLat],
  ];
}

function focusPipeline(map: Map, feature: PipelineFeature) {
  const bounds = pipelineBounds(feature);
  if (!bounds) return;

  map.fitBounds(bounds, {
    padding: { top: 70, bottom: 70, left: 70, right: 70 },
    maxZoom: 15,
    duration: 600,
  });
}

function statusTextClass(status: string) {
  if (status === "Active") return "text-success";
  if (status === "Maintenance") return "text-warning";
  if (status === "Leaking") return "text-danger";
  return "text-unknown";
}

function statusDotClass(status: string) {
  if (status === "Active") return "bg-success";
  if (status === "Maintenance") return "bg-warning";
  if (status === "Leaking") return "bg-danger";
  return "bg-unknown";
}

interface PipelineMapProps {
  selectedPipelineId?: string | null;
  onPipelineSelect?: (pipelineId: string | null) => void;
}

export default function PipelineMap({
  selectedPipelineId,
  onPipelineSelect,
}: PipelineMapProps = {}) {
  const { theme } = useTheme();
  const mapContainer = useRef<HTMLDivElement>(null);
  const mapRef = useRef<Map | null>(null);
  const pipelinesRef = useRef<PipelineFeature[]>([]);
  const selectedPipelineIdRef = useRef<string | null>(
    selectedPipelineId ?? null
  );
  const onPipelineSelectRef = useRef(onPipelineSelect);
  const mapClickRef = useRef<{ id: string; at: number } | null>(null);
  const appliedThemeRef = useRef<string | null>(null);
  const initialFitDoneRef = useRef(false);

  const [selected, setSelected] = useState<PipelineProperties | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tileWarning, setTileWarning] = useState(false);
  const [pipelineCount, setPipelineCount] = useState(0);
  const {
    generating: generatingReport,
    error: reportError,
    downloaded: downloadedReport,
    download: downloadReport,
    reset: resetReport,
  } = useReportDownload();

  useEffect(() => {
    onPipelineSelectRef.current = onPipelineSelect;
  }, [onPipelineSelect]);

  useEffect(() => {
    if (!mapContainer.current || mapRef.current) return;

    const container = mapContainer.current;
    let map: Map | null = null;
    let cancelled = false;
    let mapLoaded = false;

    async function initializeMap() {
      try {
        const geojson = await fetchAPI<PipelineGeoJSON>(
          "/api/pipelines/geojson"
        );

        if (cancelled) return;

        setPipelineCount(geojson.features.length);
        pipelinesRef.current = geojson.features;

        const initialTheme = getAppliedTheme();
        appliedThemeRef.current = initialTheme;

        map = new Map({
          container,
          style: MAP_STYLE_URLS[initialTheme],
          center: [73.8055, 18.7525],
          zoom: 12,
          minZoom: 11,
          maxZoom: 18,
          maxBounds: MAP_BOUNDS,
          attributionControl: { compact: true },
        });

        mapRef.current = map;

        map.addControl(
          new NavigationControl({
            showCompass: true,
            showZoom: true,
          }),
          "top-right"
        );

        const activeMap = map;

        const installLayers = () => {
          if (cancelled || !activeMap) return;

          const palette = getPipelineMapPalette();

          if (!activeMap.getSource("pipelines")) {
            activeMap.addSource("pipelines", {
              type: "geojson",
              data: geojson,
              promoteId: "pipeline_id",
            });
          }

          if (!activeMap.getLayer("pipeline-casing")) {
            activeMap.addLayer({
              id: "pipeline-casing",
              type: "line",
              source: "pipelines",
              layout: {
                "line-cap": "round",
                "line-join": "round",
              },
              paint: {
                "line-color": palette.casing,
                "line-width": [
                  "interpolate",
                  ["linear"],
                  ["zoom"],
                  11,
                  7,
                  14,
                  10,
                  17,
                  14,
                ],
                "line-opacity": 0.9,
              },
            });
          }

          if (!activeMap.getLayer("pipeline-lines")) {
            activeMap.addLayer({
              id: "pipeline-lines",
              type: "line",
              source: "pipelines",
              layout: {
                "line-cap": "round",
                "line-join": "round",
              },
              paint: {
                "line-color": [
                  "match",
                  ["get", "status"],
                  "Active",
                  palette.active,
                  "Maintenance",
                  palette.maintenance,
                  "Leaking",
                  palette.leaking,
                  palette.unknown,
                ],
                "line-width": [
                  "interpolate",
                  ["linear"],
                  ["zoom"],
                  11,
                  4,
                  14,
                  6.5,
                  17,
                  9.5,
                ],
                "line-opacity": 1,
              },
            });
          }

          if (!activeMap.getLayer("pipeline-hover")) {
            activeMap.addLayer({
              id: "pipeline-hover",
              type: "line",
              source: "pipelines",
              layout: {
                "line-cap": "round",
                "line-join": "round",
              },
              paint: {
                "line-color": palette.hover,
                "line-width": [
                  "interpolate",
                  ["linear"],
                  ["zoom"],
                  11,
                  6.5,
                  14,
                  9,
                  17,
                  12,
                ],
                "line-opacity": [
                  "case",
                  ["boolean", ["feature-state", "hover"], false],
                  0.3,
                  0,
                ],
              },
            });
          }

          if (!activeMap.getLayer("selected-pipeline-halo")) {
            activeMap.addLayer({
              id: "selected-pipeline-halo",
              type: "line",
              source: "pipelines",
              filter: ["==", ["get", "pipeline_id"], ""],
              layout: {
                "line-cap": "round",
                "line-join": "round",
              },
              paint: {
                "line-color": palette.selected,
                "line-width": [
                  "interpolate",
                  ["linear"],
                  ["zoom"],
                  11,
                  13,
                  14,
                  17,
                  17,
                  22,
                ],
                "line-opacity": 0.25,
              },
            });
          }

          if (!activeMap.getLayer("selected-pipeline-casing")) {
            activeMap.addLayer({
              id: "selected-pipeline-casing",
              type: "line",
              source: "pipelines",
              filter: ["==", ["get", "pipeline_id"], ""],
              layout: {
                "line-cap": "round",
                "line-join": "round",
              },
              paint: {
                "line-color": palette.selected,
                "line-width": [
                  "interpolate",
                  ["linear"],
                  ["zoom"],
                  11,
                  9.5,
                  14,
                  13,
                  17,
                  17,
                ],
                "line-opacity": 1,
              },
            });
          }

          if (!activeMap.getLayer("selected-pipeline-core")) {
            activeMap.addLayer({
              id: "selected-pipeline-core",
              type: "line",
              source: "pipelines",
              filter: ["==", ["get", "pipeline_id"], ""],
              layout: {
                "line-cap": "round",
                "line-join": "round",
              },
              paint: {
                "line-color": [
                  "match",
                  ["get", "status"],
                  "Active",
                  palette.active,
                  "Maintenance",
                  palette.maintenance,
                  "Leaking",
                  palette.leaking,
                  palette.unknown,
                ],
                "line-width": [
                  "interpolate",
                  ["linear"],
                  ["zoom"],
                  11,
                  5.5,
                  14,
                  8,
                  17,
                  11.5,
                ],
                "line-opacity": 1,
              },
            });
          }

          const selectedId = selectedPipelineIdRef.current ?? "";
          activeMap.setFilter("selected-pipeline-halo", [
            "==",
            ["get", "pipeline_id"],
            selectedId,
          ]);
          activeMap.setFilter("selected-pipeline-casing", [
            "==",
            ["get", "pipeline_id"],
            selectedId,
          ]);
          activeMap.setFilter("selected-pipeline-core", [
            "==",
            ["get", "pipeline_id"],
            selectedId,
          ]);

          if (!initialFitDoneRef.current) {
            initialFitDoneRef.current = true;

            const initialFeature = selectedId
              ? pipelinesRef.current.find(
                  (item) => item.properties.pipeline_id === selectedId
                )
              : undefined;

            if (initialFeature) {
              setSelected(initialFeature.properties);
              if (!mapClickRef.current) {
                focusPipeline(activeMap, initialFeature);
              }
            } else {
              activeMap.fitBounds(MAP_BOUNDS, {
                padding: 55,
                maxZoom: 14,
                duration: 0,
              });
            }
          }

          setLoading(false);
        };

        let hoveredPipelineId: string | number | undefined;

        activeMap.on("style.load", () => {
          if (cancelled) return;
          mapLoaded = true;
          // The style swap drops feature state, so forget the hovered id and
          // let the next mousemove re-apply it against the rebuilt source.
          hoveredPipelineId = undefined;
          installLayers();
        });

        activeMap.on("click", "pipeline-lines", (event) => {
          const feature = event.features?.[0];
          if (!feature?.properties) return;

          const properties = feature.properties as PipelineProperties;

          mapClickRef.current = {
            id: properties.pipeline_id,
            at: Date.now(),
          };
          selectedPipelineIdRef.current = properties.pipeline_id;
          setSelected(properties);
          onPipelineSelectRef.current?.(properties.pipeline_id);

          activeMap.setFilter("selected-pipeline-halo", [
            "==",
            ["get", "pipeline_id"],
            properties.pipeline_id,
          ]);
          activeMap.setFilter("selected-pipeline-casing", [
            "==",
            ["get", "pipeline_id"],
            properties.pipeline_id,
          ]);
          activeMap.setFilter("selected-pipeline-core", [
            "==",
            ["get", "pipeline_id"],
            properties.pipeline_id,
          ]);
        });

        activeMap.on("mousemove", "pipeline-lines", (event) => {
          const feature = event.features?.[0];
          if (!feature?.properties) return;

          const pipelineId = feature.properties.pipeline_id;
          if (hoveredPipelineId === pipelineId) return;

          if (hoveredPipelineId != null) {
            activeMap.setFeatureState(
              { source: "pipelines", id: hoveredPipelineId },
              { hover: false }
            );
          }

          hoveredPipelineId = pipelineId;
          activeMap.setFeatureState(
            { source: "pipelines", id: pipelineId },
            { hover: true }
          );
          activeMap.getCanvas().style.cursor = "pointer";
        });

        activeMap.on("mouseleave", "pipeline-lines", () => {
          if (hoveredPipelineId != null) {
            activeMap.setFeatureState(
              { source: "pipelines", id: hoveredPipelineId },
              { hover: false }
            );
            hoveredPipelineId = undefined;
          }
          activeMap.getCanvas().style.cursor = "";
        });

        activeMap.on("error", (event) => {
          const detail = event as unknown as {
            sourceId?: string;
            tile?: unknown;
            error?: { message?: string };
          };

          const isBasemapSource =
            detail.sourceId === "protomaps" || detail.sourceId === "osm";

          if (isBasemapSource || detail.tile) {
            console.warn(
              "Pipeline basemap tile error:",
              detail.error?.message ?? detail.error
            );
            if (!cancelled) setTileWarning(true);
            return;
          }

          console.error("Pipeline map error:", detail.error);
          if (!cancelled && !mapLoaded) {
            setError("Unable to load pipeline network map.");
            setLoading(false);
          }
        });
      } catch (err) {
        console.error("Pipeline map error:", err);
        setError("Unable to load pipeline network.");
        setLoading(false);
      }
    }

    void initializeMap();

    return () => {
      cancelled = true;
      map?.remove();
      mapRef.current = null;
      appliedThemeRef.current = null;
      initialFitDoneRef.current = false;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const activeTheme = getAppliedTheme();
    if (appliedThemeRef.current === activeTheme) return;

    appliedThemeRef.current = activeTheme;
    map.setStyle(MAP_STYLE_URLS[activeTheme]);
  }, [theme]);

  useEffect(() => {
    selectedPipelineIdRef.current = selectedPipelineId ?? null;

    const feature = selectedPipelineId
      ? pipelinesRef.current.find(
          (item) => item.properties.pipeline_id === selectedPipelineId
        )
      : undefined;

    setSelected(feature?.properties ?? null);

    const map = mapRef.current;
    if (!map || !map.getLayer("selected-pipeline-casing")) return;

    const pipelineId = selectedPipelineId ?? "";
    map.setFilter("selected-pipeline-halo", [
      "==",
      ["get", "pipeline_id"],
      pipelineId,
    ]);
    map.setFilter("selected-pipeline-casing", [
      "==",
      ["get", "pipeline_id"],
      pipelineId,
    ]);
    map.setFilter("selected-pipeline-core", [
      "==",
      ["get", "pipeline_id"],
      pipelineId,
    ]);

    if (!feature) return;

    const mapClick = mapClickRef.current;
    const clickedOnMap =
      mapClick !== null &&
      mapClick.id === selectedPipelineId &&
      Date.now() - mapClick.at < 750;

    if (clickedOnMap) {
      mapClickRef.current = null;
    } else {
      focusPipeline(map, feature);
    }
  }, [selectedPipelineId]);

  useEffect(() => {
    resetReport();
  }, [selected?.pipeline_id, resetReport]);

  const clearSelection = () => {
    selectedPipelineIdRef.current = null;
    setSelected(null);
    onPipelineSelectRef.current?.(null);

    const map = mapRef.current;
    if (!map || !map.getLayer("selected-pipeline-casing")) return;

    map.setFilter("selected-pipeline-halo", [
      "==",
      ["get", "pipeline_id"],
      "",
    ]);
    map.setFilter("selected-pipeline-casing", [
      "==",
      ["get", "pipeline_id"],
      "",
    ]);
    map.setFilter("selected-pipeline-core", [
      "==",
      ["get", "pipeline_id"],
      "",
    ]);
  };

  return (
    <div className="relative overflow-hidden rounded-xl border border-border bg-surface">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border px-4 py-4 sm:px-5">
        <div>
          <h2 className="font-semibold">Pipeline Network</h2>
          <p className="mt-1 text-xs text-muted">Chakan Industrial Zone</p>
        </div>

        <div className="flex flex-wrap gap-x-3 gap-y-1.5 text-[11px] text-muted sm:text-xs">
          <span className="flex items-center gap-1.5">
            <span
              className="h-2 w-2 rounded-full"
              style={{ backgroundColor: "var(--pipeline-active)" }}
            />
            Active
          </span>
          <span className="flex items-center gap-1.5">
            <span
              className="h-2 w-2 rounded-full"
              style={{ backgroundColor: "var(--pipeline-maintenance)" }}
            />
            Maintenance
          </span>
          <span className="flex items-center gap-1.5">
            <span
              className="h-2 w-2 rounded-full"
              style={{ backgroundColor: "var(--pipeline-leaking)" }}
            />
            Leaking
          </span>
          <span className="flex items-center gap-1.5">
            <span
              className="h-2 w-2 rounded-full"
              style={{ backgroundColor: "var(--pipeline-unknown)" }}
            />
            Unknown
          </span>
        </div>
      </div>

      <div className="relative">
        <div
          ref={mapContainer}
          className="h-[320px] w-full bg-map-background sm:h-[400px] lg:h-[480px] xl:h-[560px]"
        />

        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-surface-sunken text-sm text-muted">
            Loading pipeline network...
          </div>
        )}

        {error && (
          <div className="absolute inset-0 flex items-center justify-center bg-surface-sunken px-6 text-center text-sm text-danger">
            {error}
          </div>
        )}

        {tileWarning && !error && (
          <div className="absolute left-3 top-3 z-10 max-w-[calc(100%-5.5rem)] rounded-md border border-warning/30 bg-surface-overlay/95 px-2.5 py-1.5 text-[11px] leading-4 text-warning">
            Some basemap tiles failed to load
          </div>
        )}

        {selected && (
          <div className="border-t border-border bg-surface p-4 sm:p-5 lg:absolute lg:bottom-5 lg:left-5 lg:z-10 lg:w-80 lg:rounded-xl lg:border lg:bg-surface-overlay/95 lg:shadow-xl lg:backdrop-blur">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-xs text-muted">SELECTED PIPELINE</p>
                <h3 className="mt-1 break-all font-semibold">
                  {selected.pipeline_id}
                </h3>
              </div>

              <button
                type="button"
                onClick={clearSelection}
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-muted transition hover:bg-surface-hover hover:text-foreground"
                aria-label="Close pipeline details"
              >
                <span className="text-lg leading-none">×</span>
              </button>
            </div>

            <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 text-sm lg:grid-cols-1">
              <div className="min-w-0">
                <p className="text-[11px] uppercase tracking-wide text-muted">
                  Type
                </p>
                <p className="mt-0.5 break-words">{selected.type}</p>
              </div>
              <div className="min-w-0">
                <p className="text-[11px] uppercase tracking-wide text-muted">
                  Status
                </p>
                <p
                  className={`mt-0.5 flex items-center gap-1.5 ${statusTextClass(
                    selected.status
                  )}`}
                >
                  <span
                    className={`h-1.5 w-1.5 rounded-full ${statusDotClass(
                      selected.status
                    )}`}
                  />
                  {selected.status}
                </p>
              </div>
              <div className="min-w-0">
                <p className="text-[11px] uppercase tracking-wide text-muted">
                  Material
                </p>
                <p className="mt-0.5 break-words">{selected.material}</p>
              </div>
              <div className="min-w-0">
                <p className="text-[11px] uppercase tracking-wide text-muted">
                  Pressure
                </p>
                <p className="mt-0.5">{selected.pressure_bar} bar</p>
              </div>
              <div className="min-w-0">
                <p className="text-[11px] uppercase tracking-wide text-muted">
                  Depth
                </p>
                <p className="mt-0.5">{selected.depth_m} m</p>
              </div>
              <div className="min-w-0">
                <p className="text-[11px] uppercase tracking-wide text-muted">
                  Installed
                </p>
                <p className="mt-0.5">{selected.installed}</p>
              </div>
            </div>

            <button
              type="button"
              disabled={generatingReport}
              onClick={() => void downloadReport(selected.pipeline_id)}
              className="mt-4 w-full rounded-lg bg-accent px-3 py-2.5 text-xs font-semibold text-accent-contrast transition hover:bg-accent-strong disabled:cursor-not-allowed disabled:opacity-50"
            >
              {generatingReport ? "Generating PDF..." : "Download PDF Report"}
            </button>

            {downloadedReport === selected.pipeline_id && (
              <p className="mt-2 text-xs text-success">
                Report downloaded.
              </p>
            )}
            {reportError && (
              <p className="mt-2 text-xs text-danger">{reportError}</p>
            )}
          </div>
        )}
      </div>

      <div className="flex flex-wrap justify-between gap-2 border-t border-border px-4 py-3 text-xs text-muted sm:px-5">
        <span>{pipelineCount} pipeline routes loaded</span>
        <span>Select a route or use the directory below</span>
      </div>
    </div>
  );
}
