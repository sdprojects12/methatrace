"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { fetchAPI } from "../../src/lib/api";

interface SensorReading {
  pipeline_id: string;
  pressure_bar: number | null;
  flow_rate_m3h: number | null;
  baseline_pressure_bar: number | null;
  baseline_flow_rate_m3h: number | null;
  pressure_delta_bar: number | null;
  flow_delta_m3h: number | null;
  sensor_status: string | null;
  is_anomaly: boolean;
  synthetic: boolean;
  scenario?: string | null;
}

interface SensorFleetResponse {
  monitored: number;
  alerts: number;
  alert_ids: string[];
  simulated: boolean;
  readings: SensorReading[];
}

const ALL_FILTER = "All";

function formatValue(value: number | null, suffix = "") {
  return value == null || !Number.isFinite(value) ? "—" : `${value}${suffix}`;
}

function statusClass(status: string | null) {
  if (status === "NORMAL") return "text-success";
  if (status?.startsWith("CRITICAL")) return "text-danger";
  return "text-secondary";
}

function statusDotClass(status: string | null) {
  if (status === "NORMAL") return "bg-success";
  if (status?.startsWith("CRITICAL")) return "bg-danger";
  return "bg-unknown";
}

function SummaryCard({
  label,
  value,
  detail,
  accent,
}: {
  label: string;
  value: string;
  detail: string;
  accent: string;
}) {
  return (
    <div className="rounded-xl border border-border bg-surface p-5">
      <p className="text-sm text-muted">{label}</p>
      <p className={`mt-3 text-3xl font-semibold tracking-tight ${accent}`}>
        {value}
      </p>
      <p className="mt-2 text-xs text-muted">{detail}</p>
    </div>
  );
}

function ReadingValue({
  label,
  value,
}: {
  label: string;
  value: string | number | boolean | null | undefined;
}) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-border-subtle py-2 last:border-0">
      <span className="text-muted">{label}</span>
      <span className="text-right text-secondary">
        {value == null ? "—" : String(value)}
      </span>
    </div>
  );
}

export default function SensorsPage() {
  const [fleet, setFleet] = useState<SensorFleetResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState(0);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState(ALL_FILTER);
  const [selectedPipelineId, setSelectedPipelineId] = useState<string | null>(
    null
  );
  const [selectedReading, setSelectedReading] =
    useState<SensorReading | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const detailRequestId = useRef(0);
  const detailController = useRef<AbortController | null>(null);

  useEffect(() => {
    let cancelled = false;

    fetchAPI<SensorFleetResponse>("/api/sensors")
      .then((result) => {
        if (!cancelled) { setFleet(result); setLastUpdated(new Date()); }
      })
      .catch((requestError) => {
        if (!cancelled) {
          console.error("Sensor fleet API error:", requestError);
          setError("Unable to load sensor readings.");
          setFleet(null);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [retryCount]);

  const readings = useMemo(() => fleet?.readings ?? [], [fleet]);
  const statuses = useMemo(
    () => [ALL_FILTER, ...new Set(readings.map((reading) => reading.sensor_status).filter(Boolean) as string[])],
    [readings]
  );
  const filteredReadings = useMemo(() => {
    const query = search.trim().toLowerCase();
    return readings.filter((reading) => {
      const matchesSearch = reading.pipeline_id.toLowerCase().includes(query);
      const matchesStatus =
        statusFilter === ALL_FILTER || reading.sensor_status === statusFilter;
      return matchesSearch && matchesStatus;
    });
  }, [readings, search, statusFilter]);

  const selectPipeline = (pipelineId: string) => {
    detailController.current?.abort();
    const requestId = detailRequestId.current + 1;
    detailRequestId.current = requestId;
    const controller = new AbortController();
    detailController.current = controller;

    setSelectedPipelineId(pipelineId);
    setSelectedReading(null);
    setDetailError(null);
    setDetailLoading(true);

    fetchAPI<SensorReading>(`/api/sensors/${encodeURIComponent(pipelineId)}`, { signal: controller.signal })
      .then((reading) => {
        if (detailRequestId.current !== requestId) return;
        setSelectedReading(reading);
      })
      .catch((requestError) => {
        if (detailRequestId.current !== requestId || controller.signal.aborted) return;
        console.error(`Sensor API error for ${pipelineId}:`, requestError);
        setDetailError("Unable to load this sensor reading.");
      })
      .finally(() => {
        if (detailRequestId.current !== requestId) return;
        detailController.current = null;
        setDetailLoading(false);
      });
  };

  const clearFilters = () => {
    setSearch("");
    setStatusFilter(ALL_FILTER);
  };

  const retryConnection = () => {
    setLoading(true);
    setError(null);
    setRetryCount((count) => count + 1);
  };

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
        <h3 className="text-2xl font-semibold tracking-tight">
          Sensor Monitoring
        </h3>
        <p className="mt-2 text-sm text-muted">
          Current telemetry readings across monitored pipeline segments.
        </p>
        </div>
        <div className="flex items-center gap-3">
          {lastUpdated && <span className="text-xs text-muted">Fetched {lastUpdated.toLocaleTimeString()}</span>}
          <button type="button" onClick={retryConnection} disabled={loading} aria-busy={loading} className="rounded-lg border border-border px-3 py-2 text-xs text-secondary hover:bg-surface-hover disabled:opacity-60">{loading ? "Refreshing…" : "Refresh data"}</button>
        </div>
      </div>

      {loading ? (
        <div className="rounded-xl border border-border bg-surface p-6 text-sm text-muted">
          Loading sensor readings...
        </div>
      ) : error ? (
        <div className="rounded-xl border border-danger/25 bg-danger/5 p-6">
          <p className="text-sm text-danger">{error}</p>
          <button
            type="button"
            onClick={retryConnection}
            className="mt-4 rounded-lg border border-danger/30 bg-danger/10 px-4 py-2 text-sm text-danger transition hover:bg-danger/20"
          >
            Retry Connection
          </button>
        </div>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <SummaryCard
              label="Monitored Pipelines"
              value={String(fleet?.monitored ?? readings.length)}
              detail="Current fleet-wide sensor readings"
              accent="text-foreground"
            />
            <SummaryCard
              label="Normal Readings"
              value={String(Math.max(0, (fleet?.monitored ?? 0) - (fleet?.alerts ?? 0)))}
              detail="Readings without an active alert"
              accent="text-success"
            />
            <SummaryCard
              label="Critical Alerts"
              value={String(fleet?.alerts ?? 0)}
              detail="Backend-reported sensor alerts"
              accent="text-danger"
            />
          </div>

          <section className="rounded-xl border border-border bg-surface">
            <div className="border-b border-border p-6">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <h3 className="font-semibold">Sensor Readings</h3>
                  <p className="mt-1 text-xs text-muted">
                    Select a pipeline to load its individual reading.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={clearFilters}
                  className="rounded-lg border border-border px-3 py-2 text-xs text-muted transition hover:bg-surface-hover hover:text-foreground"
                >
                  Clear filters
                </button>
              </div>

              <div className="mt-5 flex flex-wrap gap-3">
                <label className="flex min-w-0 flex-1 flex-col gap-2 text-xs text-muted sm:min-w-56">
                  Search by pipeline ID
                  <input
                    type="search"
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    placeholder="Pipeline ID"
                    className="rounded-lg border border-border bg-surface-sunken px-3 py-2.5 text-sm text-secondary outline-none placeholder:text-subtle focus:border-accent/60"
                  />
                </label>
                <label className="flex min-w-0 flex-1 flex-col gap-2 text-xs text-muted sm:min-w-52">
                  Filter by status
                  <select
                    value={statusFilter}
                    onChange={(event) => setStatusFilter(event.target.value)}
                    className="rounded-lg border border-border bg-surface-sunken px-3 py-2.5 text-sm text-secondary outline-none focus:border-accent/60"
                  >
                    {statuses.map((status) => (
                      <option key={status} value={status}>
                        {status}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            </div>

            {filteredReadings.length === 0 ? (
              <div className="p-6 text-sm text-muted">
                {readings.length === 0
                  ? "No sensor readings are available."
                  : "No readings match the selected search and filter."}
              </div>
            ) : (
              <div className="divide-y divide-border-subtle">
                {filteredReadings.map((reading) => (
                  <button
                    key={reading.pipeline_id}
                    type="button"
                    onClick={() => selectPipeline(reading.pipeline_id)}
                    aria-pressed={selectedPipelineId === reading.pipeline_id}
                    className={`grid w-full grid-cols-2 gap-x-4 gap-y-3 px-4 py-4 text-left transition hover:bg-surface-hover sm:px-6 md:grid-cols-3 xl:grid-cols-5 ${
                      selectedPipelineId === reading.pipeline_id
                        ? "bg-accent/5 ring-1 ring-inset ring-accent/30"
                        : ""
                    }`}
                  >
                    <div className="col-span-2 min-w-0 sm:col-span-1">
                      <p className="text-xs text-muted">Pipeline ID</p>
                      <p className="mt-1 break-all font-medium text-foreground">
                        {reading.pipeline_id}
                      </p>
                    </div>
                    <div className="min-w-0">
                      <p className="text-xs text-muted">Pressure</p>
                      <p className="mt-1 text-sm text-secondary">
                        {formatValue(reading.pressure_bar, " bar")}
                      </p>
                    </div>
                    <div className="min-w-0">
                      <p className="text-xs text-muted">Flow rate</p>
                      <p className="mt-1 text-sm text-secondary">
                        {formatValue(reading.flow_rate_m3h, " m³/h")}
                      </p>
                    </div>
                    <div className="min-w-0">
                      <p className="text-xs text-muted">Status</p>
                      <p
                        className={`mt-1 flex items-center gap-1.5 text-sm ${statusClass(
                          reading.sensor_status
                        )}`}
                      >
                        <span
                          className={`h-1.5 w-1.5 rounded-full ${statusDotClass(
                            reading.sensor_status
                          )}`}
                        />
                        {reading.sensor_status ?? "—"}
                      </p>
                    </div>
                    <div className="min-w-0">
                      <p className="text-xs text-muted">Alert</p>
                      <p className="mt-1 text-sm text-secondary">
                        {reading.is_anomaly ? "Active" : "None"}
                      </p>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </section>

          {selectedPipelineId && (
            <section className="rounded-xl border border-border bg-surface p-6">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="text-xs uppercase tracking-widest text-muted">
                    Individual Sensor Reading
                  </p>
                  <h3 className="mt-1 text-xl font-semibold">
                    {selectedPipelineId}
                  </h3>
                </div>
                <span className="rounded-full border border-warning/25 bg-warning/10 px-3 py-2 text-xs text-warning">
                  Simulated telemetry
                </span>
              </div>

              {detailLoading ? (
                <p className="mt-6 text-sm text-muted">
                  Loading individual reading...
                </p>
              ) : detailError ? (
                <div className="mt-6 space-y-3" role="alert">
                  <p className="text-sm text-danger">{detailError}</p>
                  <button type="button" onClick={() => selectPipeline(selectedPipelineId)} className="rounded-lg border border-danger/30 bg-danger/5 px-3 py-2 text-xs text-danger hover:bg-danger/10">
                    Retry reading
                  </button>
                </div>
              ) : selectedReading ? (
                <div className="mt-6 grid gap-x-8 gap-y-1 sm:grid-cols-2">
                  <ReadingValue label="Pipeline ID" value={selectedReading.pipeline_id} />
                  <ReadingValue label="Sensor status" value={selectedReading.sensor_status} />
                  <ReadingValue label="Pressure (bar)" value={formatValue(selectedReading.pressure_bar)} />
                  <ReadingValue label="Flow rate (m³/h)" value={formatValue(selectedReading.flow_rate_m3h)} />
                  <ReadingValue label="Baseline pressure (bar)" value={formatValue(selectedReading.baseline_pressure_bar)} />
                  <ReadingValue label="Baseline flow rate (m³/h)" value={formatValue(selectedReading.baseline_flow_rate_m3h)} />
                  <ReadingValue label="Pressure delta (bar)" value={formatValue(selectedReading.pressure_delta_bar)} />
                  <ReadingValue label="Flow delta (m³/h)" value={formatValue(selectedReading.flow_delta_m3h)} />
                  <ReadingValue label="Scenario" value={selectedReading.scenario} />
                  <ReadingValue label="Alert active" value={selectedReading.is_anomaly ? "Yes" : "No"} />
                  <ReadingValue label="Synthetic reading" value={selectedReading.synthetic ? "Yes" : "No"} />
                </div>
              ) : null}
            </section>
          )}

          <div className="rounded-xl border border-warning/25 bg-warning/5 p-5">
            <h4 className="text-sm font-medium text-warning">
              Simulated Telemetry Notice
            </h4>
            <p className="mt-1 text-xs leading-6 text-muted">
              These readings are explicitly marked as simulated by the backend
              and do not represent verified physical sensor measurements.
            </p>
          </div>
        </>
      )}
    </div>
  );
}
