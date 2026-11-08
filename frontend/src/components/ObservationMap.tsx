"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Map,
  NavigationControl,
  setWorkerUrl,
  type GeoJSONSource,
} from "maplibre-gl";
import type { Feature, FeatureCollection, Point } from "geojson";
import { getAppliedTheme, useTheme } from "./ThemeProvider";
import {
  MAP_STYLE_URLS,
  getObservationMapPalette,
} from "../lib/mapTheme";

setWorkerUrl("/maplibre-gl-worker.mjs");

export interface ObservationMapRecord {
  observation_id: string;
  timestamp: string | null;
  latitude: number | null;
  longitude: number | null;
  methane_concentration_ppm: number | null;
  wind_speed_kmh: number | null;
  wind_direction_deg: number | null;
  source_label: string | null;
  is_threshold_anomaly: boolean | null;
  is_ml_anomaly: boolean | null;
  pipeline_id: string | null;
}

interface ObservationMapProps {
  observations: ObservationMapRecord[];
  selectedObservationId?: string | null;
  onObservationSelect?: (observationId: string | null) => void;
}

type ObservationProperties = Omit<
  ObservationMapRecord,
  "latitude" | "longitude"
> & {
  latitude: number;
  longitude: number;
};

type ObservationGeoJSON = FeatureCollection<Point, ObservationProperties>;

const FALLBACK_CENTER: [number, number] = [73.8055, 18.7525];
// Use PipelineMap's exact extent for the initial view. Keep slightly wider
// movement bounds so valid edge observations remain reachable.
const CHAKAN_BOUNDS: [[number, number], [number, number]] = [
  [73.771, 18.695],
  [73.84, 18.81],
];
const MAP_BOUNDS: [[number, number], [number, number]] = [
  [73.761, 18.685],
  [73.85, 18.82],
];

function isMappable(
  observation: ObservationMapRecord
): observation is ObservationProperties {
  return (
    typeof observation.latitude === "number" &&
    Number.isFinite(observation.latitude) &&
    typeof observation.longitude === "number" &&
    Number.isFinite(observation.longitude)
  );
}

function formatValue(value: number | null, suffix = "") {
  return value == null || !Number.isFinite(value) ? "—" : `${value}${suffix}`;
}

function observationStatus(observation: ObservationProperties) {
  if (observation.is_threshold_anomaly && observation.is_ml_anomaly) {
    return "Both";
  }
  if (observation.is_threshold_anomaly) return "Threshold";
  if (observation.is_ml_anomaly) return "ML";
  return "Normal";
}

function statusTextClass(status: string) {
  if (status === "Both") return "text-danger";
  if (status === "Normal") return "text-success";
  return "text-warning";
}

function statusDotClass(status: string) {
  if (status === "Both") return "bg-danger";
  if (status === "Normal") return "bg-success";
  if (status === "ML") return "bg-warning ring-1 ring-danger";
  return "bg-warning";
}

function focusObservation(map: Map, observation: ObservationProperties) {
  map.easeTo({
    center: [observation.longitude, observation.latitude],
    zoom: Math.max(map.getZoom(), 15),
    duration: 500,
  });
}

export default function ObservationMap({
  observations,
  selectedObservationId,
  onObservationSelect,
}: ObservationMapProps) {
  const { theme } = useTheme();
  const mapContainer = useRef<HTMLDivElement>(null);
  const mapRef = useRef<Map | null>(null);
  const observationsRef = useRef<ObservationProperties[]>([]);
  const selectedObservationIdRef = useRef<string | null>(
    selectedObservationId ?? null
  );
  const onObservationSelectRef = useRef(onObservationSelect);
  const mapClickRef = useRef<{ id: string; at: number } | null>(null);
  const appliedThemeRef = useRef<string | null>(null);
  const initialFitDoneRef = useRef(false);
  const [selected, setSelected] = useState<ObservationProperties | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tileWarning, setTileWarning] = useState(false);
  const mappableCount = useMemo(
    () => observations.filter(isMappable).length,
    [observations]
  );

  useEffect(() => {
    onObservationSelectRef.current = onObservationSelect;
  }, [onObservationSelect]);

  useEffect(() => {
    selectedObservationIdRef.current = selectedObservationId ?? null;
    const observation = observationsRef.current.find(
      (item) => item.observation_id === selectedObservationId
    );
    setSelected(observation ?? null);

    const map = mapRef.current;
    if (!map || !map.getLayer("selected-observation")) return;

    const observationId = selectedObservationId ?? "";
    map.setFilter("selected-observation-halo", [
      "==",
      ["get", "observation_id"],
      observationId,
    ]);
    map.setFilter("selected-observation", [
      "==",
      ["get", "observation_id"],
      observationId,
    ]);

    if (!observation) return;

    const mapClick = mapClickRef.current;
    const clickedOnMap =
      mapClick !== null &&
      mapClick.id === selectedObservationId &&
      Date.now() - mapClick.at < 750;

    if (clickedOnMap) {
      mapClickRef.current = null;
    } else {
      focusObservation(map, observation);
    }
  }, [selectedObservationId]);

  useEffect(() => {
    if (!mapContainer.current || mapRef.current) return;

    const container = mapContainer.current;
    let cancelled = false;
    let mapLoaded = false;
    setTileWarning(false);
    initialFitDoneRef.current = false;
    const mappableObservations = observations.filter(isMappable);
    observationsRef.current = mappableObservations;

    if (
      selectedObservationIdRef.current &&
      !mappableObservations.some(
        (item) => item.observation_id === selectedObservationIdRef.current
      )
    ) {
      setSelected(null);
    }

    const features: Feature<Point, ObservationProperties>[] =
      mappableObservations.map((observation) => ({
        type: "Feature",
        geometry: {
          type: "Point",
          coordinates: [observation.longitude, observation.latitude],
        },
        properties: observation,
      }));
    const geojson: ObservationGeoJSON = {
      type: "FeatureCollection",
      features,
    };

    async function initializeMap() {
      try {
        const initialTheme = getAppliedTheme();
        appliedThemeRef.current = initialTheme;

        const map = new Map({
          container,
          // CARTO's keyless vector styles. The public raster endpoints now
          // return an "API KEY REQUIRED" watermark, so the vector styles are
          // used instead. Both ship the OSM + CARTO attribution.
          style: MAP_STYLE_URLS[initialTheme],
          center: FALLBACK_CENTER,
          zoom: 11,
          minZoom: 9,
          maxZoom: 18,
          maxBounds: MAP_BOUNDS,
          attributionControl: { compact: true },
        });

        mapRef.current = map;
        map.addControl(new NavigationControl(), "top-right");

        // Re-installs the observation source, layers and selection filters.
        // Called on the first style load and again after every theme-driven
        // `setStyle`, so the map instance (and its handlers) is never rebuilt.
        const installLayers = () => {
          if (cancelled) return;

          const palette = getObservationMapPalette();

          if (!map.getSource("observations")) {
            map.addSource("observations", {
              type: "geojson",
              data: geojson,
              cluster: true,
              // The fitBounds view stays above this level; clusters only
              // appear at the lowest available zoom.
              clusterMaxZoom: 9,
              clusterRadius: 28,
              clusterMinPoints: 2,
            });
          }

          if (!map.getLayer("observation-clusters")) {
            map.addLayer({
              id: "observation-clusters",
              type: "circle",
              source: "observations",
              filter: ["has", "point_count"],
              paint: {
                "circle-color": palette.clusterFill,
                "circle-radius": [
                  "step",
                  ["get", "point_count"],
                  9,
                  10,
                  12,
                  50,
                  14,
                  100,
                  18,
                ],
                "circle-stroke-color": palette.clusterStroke,
                "circle-stroke-width": 1.5,
                "circle-opacity": 0.78,
              },
            });
          }

          if (!map.getLayer("normal-observations")) {
            map.addLayer({
              id: "normal-observations",
              type: "circle",
              source: "observations",
              filter: [
                "all",
                ["!", ["has", "point_count"]],
                ["!=", ["get", "is_threshold_anomaly"], true],
                ["!=", ["get", "is_ml_anomaly"], true],
              ],
              paint: {
                "circle-color": palette.normal,
                "circle-radius": [
                  "interpolate",
                  ["linear"],
                  ["zoom"],
                  10,
                  2.75,
                  14,
                  4,
                  18,
                  5.5,
                ],
                "circle-stroke-color": palette.stroke,
                "circle-stroke-width": 1.25,
              },
            });
          }

          if (!map.getLayer("threshold-observations")) {
            map.addLayer({
              id: "threshold-observations",
              type: "circle",
              source: "observations",
              filter: [
                "all",
                ["!", ["has", "point_count"]],
                ["==", ["get", "is_threshold_anomaly"], true],
                ["!=", ["get", "is_ml_anomaly"], true],
              ],
              paint: {
                "circle-color": palette.threshold,
                "circle-radius": [
                  "interpolate",
                  ["linear"],
                  ["zoom"],
                  10,
                  3.25,
                  14,
                  4.75,
                  18,
                  6.5,
                ],
                "circle-stroke-color": palette.stroke,
                "circle-stroke-width": 1.25,
              },
            });
          }

          if (!map.getLayer("ml-observations")) {
            map.addLayer({
              id: "ml-observations",
              type: "circle",
              source: "observations",
              filter: [
                "all",
                ["!", ["has", "point_count"]],
                ["!=", ["get", "is_threshold_anomaly"], true],
                ["==", ["get", "is_ml_anomaly"], true],
              ],
              paint: {
                // Sky blue distinguishes ML-only detections from amber threshold points.
                "circle-color": palette.mlFill,
                "circle-radius": [
                  "interpolate",
                  ["linear"],
                  ["zoom"],
                  10,
                  3.25,
                  14,
                  4.75,
                  18,
                  6.5,
                ],
                "circle-stroke-color": palette.mlRing,
                "circle-stroke-width": 1.75,
              },
            });
          }

          if (!map.getLayer("both-observations")) {
            map.addLayer({
              id: "both-observations",
              type: "circle",
              source: "observations",
              filter: [
                "all",
                ["!", ["has", "point_count"]],
                ["==", ["get", "is_threshold_anomaly"], true],
                ["==", ["get", "is_ml_anomaly"], true],
              ],
              paint: {
                "circle-color": palette.both,
                "circle-radius": [
                  "interpolate",
                  ["linear"],
                  ["zoom"],
                  10,
                  4,
                  14,
                  5.75,
                  18,
                  7.5,
                ],
                "circle-stroke-color": palette.stroke,
                "circle-stroke-width": 1.25,
              },
            });
          }

          if (!map.getLayer("selected-observation-halo")) {
            map.addLayer({
              id: "selected-observation-halo",
              type: "circle",
              source: "observations",
              filter: ["==", ["get", "observation_id"], ""],
              paint: {
                "circle-color": palette.halo,
                "circle-radius": 17,
                "circle-opacity": 0.22,
              },
            });
          }

          if (!map.getLayer("selected-observation")) {
            map.addLayer({
              id: "selected-observation",
              type: "circle",
              source: "observations",
              filter: ["==", ["get", "observation_id"], ""],
              paint: {
                "circle-color": palette.selected,
                "circle-radius": 8,
                "circle-stroke-color": palette.selectedStroke,
                "circle-stroke-width": 2.5,
              },
            });
          }

          const observationId = selectedObservationIdRef.current ?? "";
          map.setFilter("selected-observation-halo", [
            "==",
            ["get", "observation_id"],
            observationId,
          ]);
          map.setFilter("selected-observation", [
            "==",
            ["get", "observation_id"],
            observationId,
          ]);

          if (!initialFitDoneRef.current) {
            initialFitDoneRef.current = true;

            const initialObservation = selectedObservationIdRef.current
              ? observationsRef.current.find(
                  (item) =>
                    item.observation_id === selectedObservationIdRef.current
                )
              : undefined;

            if (initialObservation && !mapClickRef.current) {
              setSelected(initialObservation);
              focusObservation(map, initialObservation);
            } else {
              map.fitBounds(CHAKAN_BOUNDS, {
                padding: 55,
                maxZoom: 14,
                duration: 0,
              });
            }
          }

          setLoading(false);
        };

        map.on("style.load", () => {
          if (cancelled) return;
          mapLoaded = true;
          installLayers();
        });

        const pointLayers = [
          "normal-observations",
          "threshold-observations",
          "ml-observations",
          "both-observations",
        ];

        map.on("click", pointLayers, (event) => {
          const properties = event.features?.[0]?.properties as
            | ObservationProperties
            | undefined;
          if (!properties) return;

          mapClickRef.current = {
            id: properties.observation_id,
            at: Date.now(),
          };
          selectedObservationIdRef.current = properties.observation_id;
          setSelected(properties);
          onObservationSelectRef.current?.(properties.observation_id);
          map.setFilter("selected-observation-halo", [
            "==",
            ["get", "observation_id"],
            properties.observation_id,
          ]);
          map.setFilter("selected-observation", [
            "==",
            ["get", "observation_id"],
            properties.observation_id,
          ]);
        });

        map.on("click", "observation-clusters", (event) => {
          const feature = event.features?.[0];
          const clusterId = feature?.properties?.cluster_id;
          if (!feature || clusterId == null) return;

          const source = map.getSource("observations") as
            | GeoJSONSource
            | undefined;
          if (!source) return;

          source
            .getClusterExpansionZoom(clusterId)
            .then((zoom) => {
              if (cancelled) return;
              const coordinates = (feature.geometry as Point)
                .coordinates as [number, number];
              map.easeTo({
                center: coordinates,
                zoom,
                duration: 400,
              });
            })
            .catch((clusterError) => {
              console.warn(
                "Unable to expand observation cluster:",
                clusterError
              );
            });
        });

        map.on("mouseenter", pointLayers, () => {
          map.getCanvas().style.cursor = "pointer";
        });
        map.on("mouseenter", "observation-clusters", () => {
          map.getCanvas().style.cursor = "pointer";
        });
        map.on("mouseleave", pointLayers, () => {
          map.getCanvas().style.cursor = "";
        });
        map.on("mouseleave", "observation-clusters", () => {
          map.getCanvas().style.cursor = "";
        });

        map.on("error", (event) => {
          const detail = event as unknown as {
            sourceId?: string;
            tile?: unknown;
            error?: { message?: string };
          };

          const isBasemapSource =
            detail.sourceId === "protomaps" || detail.sourceId === "osm";

          if (isBasemapSource || detail.tile) {
            console.warn(
              "Observation basemap tile error:",
              detail.error?.message ?? detail.error
            );
            if (!cancelled) setTileWarning(true);
            return;
          }

          console.error("Observation map error:", detail.error);
          if (!cancelled && !mapLoaded) {
            setError("Unable to load observation map.");
            setLoading(false);
          }
        });
      } catch (mapError) {
        console.error("Observation map initialization error:", mapError);
        setError("Unable to load observation map.");
        setLoading(false);
      }
    }

    void initializeMap();

    return () => {
      cancelled = true;
      mapRef.current?.remove();
      mapRef.current = null;
      appliedThemeRef.current = null;
      initialFitDoneRef.current = false;
    };
  }, [observations]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const activeTheme = getAppliedTheme();
    if (appliedThemeRef.current === activeTheme) return;

    appliedThemeRef.current = activeTheme;
    map.setStyle(MAP_STYLE_URLS[activeTheme]);
  }, [theme]);

  return (
    <div className="relative overflow-hidden rounded-xl border border-border bg-surface">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border px-4 py-4 sm:px-5">
        <div>
          <h2 className="font-semibold">Observation Map</h2>
          <p className="mt-1 text-xs text-muted">
            Observations with valid coordinates
          </p>
        </div>
        <div className="flex flex-wrap gap-x-3 gap-y-1.5 text-[11px] text-muted sm:text-xs">
          <span className="flex items-center gap-1.5">
            <span
              className="h-2 w-2 rounded-full"
              style={{ backgroundColor: "var(--obs-normal)" }}
            />
            Normal
          </span>
          <span className="flex items-center gap-1.5">
            <span
              className="h-2 w-2 rounded-full"
              style={{ backgroundColor: "var(--obs-threshold)" }}
            />
            Threshold
          </span>
          <span className="flex items-center gap-1.5">
            <span
              className="h-2.5 w-2.5 rounded-full border-2"
              style={{
                borderColor: "var(--obs-ml-ring)",
                backgroundColor: "var(--obs-ml-fill)",
              }}
            />
            ML
          </span>
          <span className="flex items-center gap-1.5">
            <span
              className="h-2 w-2 rounded-full"
              style={{ backgroundColor: "var(--obs-both)" }}
            />
            Both
          </span>
          <span className="flex items-center gap-1.5">
            <span
              className="h-2.5 w-2.5 rounded-full border-2"
              style={{
                borderColor: "var(--obs-cluster-stroke)",
                backgroundColor: "var(--obs-cluster-fill)",
              }}
            />
            Cluster
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
            Loading observation map...
          </div>
        )}

        {error && (
          <div className="absolute inset-0 flex items-center justify-center bg-surface-sunken px-6 text-center text-sm text-danger">
            {error}
          </div>
        )}

        {!loading && !error && mappableCount === 0 && (
          <div className="absolute inset-0 flex items-center justify-center bg-surface-sunken/90 px-6 text-center text-sm text-muted">
            No observations with valid coordinates to map.
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
                <p className="text-xs text-muted">SELECTED OBSERVATION</p>
                <h3 className="mt-1 break-all font-semibold">
                  {selected.observation_id}
                </h3>
              </div>
              <button
                type="button"
                onClick={() => {
                  setSelected(null);
                  onObservationSelectRef.current?.(null);
                  const map = mapRef.current;
                  if (!map?.getLayer("selected-observation")) return;
                  map.setFilter("selected-observation-halo", [
                    "==",
                    ["get", "observation_id"],
                    "",
                  ]);
                  map.setFilter("selected-observation", [
                    "==",
                    ["get", "observation_id"],
                    "",
                  ]);
                }}
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-muted transition hover:bg-surface-hover hover:text-foreground"
                aria-label="Close observation details"
              >
                <span className="text-lg leading-none">×</span>
              </button>
            </div>

            <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 text-sm lg:grid-cols-1">
              <div className="col-span-2 min-w-0 lg:col-span-1">
                <p className="text-[11px] uppercase tracking-wide text-muted">
                  Timestamp
                </p>
                <p className="mt-0.5 break-words">
                  {selected.timestamp ?? "—"}
                </p>
              </div>
              <div className="min-w-0">
                <p className="text-[11px] uppercase tracking-wide text-muted">
                  Concentration
                </p>
                <p className="mt-0.5">
                  {formatValue(
                    selected.methane_concentration_ppm,
                    " ppm"
                  )}
                </p>
              </div>
              <div className="min-w-0">
                <p className="text-[11px] uppercase tracking-wide text-muted">
                  Anomaly
                </p>
                <p
                  className={`mt-0.5 flex items-center gap-1.5 ${statusTextClass(
                    observationStatus(selected)
                  )}`}
                >
                  <span
                    className={`h-1.5 w-1.5 rounded-full ${statusDotClass(
                      observationStatus(selected)
                    )}`}
                  />
                  {observationStatus(selected)}
                </p>
              </div>
              <div className="min-w-0">
                <p className="text-[11px] uppercase tracking-wide text-muted">
                  Source
                </p>
                <p className="mt-0.5 break-words">
                  {selected.source_label ?? "—"}
                </p>
              </div>
              <div className="min-w-0">
                <p className="text-[11px] uppercase tracking-wide text-muted">
                  Wind
                </p>
                <p className="mt-0.5">
                  {formatValue(selected.wind_speed_kmh, " km/h")} ·{" "}
                  {formatValue(selected.wind_direction_deg, "°")}
                </p>
              </div>
              <div className="col-span-2 min-w-0 lg:col-span-1">
                <p className="text-[11px] uppercase tracking-wide text-muted">
                  Pipeline
                </p>
                <p className="mt-0.5 break-words">
                  {selected.pipeline_id ?? "Unattributed"}
                </p>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="flex flex-wrap justify-between gap-2 border-t border-border px-4 py-3 text-xs text-muted sm:px-5">
        <span>{mappableCount} observations with valid coordinates</span>
        <span>Clusters expand on click · select a point for details</span>
      </div>
    </div>
  );
}
