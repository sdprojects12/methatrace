"use client";

import { useEffect, useMemo, useState } from "react";
import ObservationMap, {
  type ObservationMapRecord,
} from "../../src/components/ObservationMap";
import { fetchAPI } from "../../src/lib/api";

interface Observation extends ObservationMapRecord {
  ml_anomaly_score: number | null;
  distance_m: number | null;
}

interface ObservationsResponse {
  total: number;
  limit: number;
  offset: number;
  observations: Observation[];
}

const ALL_FILTER = "All";

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

function SelectField({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="flex min-w-0 flex-1 flex-col gap-2 text-xs text-muted sm:min-w-44">
      {label}
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="rounded-lg border border-border bg-surface-sunken px-3 py-2.5 text-sm text-secondary outline-none focus:border-accent/60"
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </label>
  );
}

function formatNumber(value: number | null, digits = 1) {
  return value == null || !Number.isFinite(value) ? "—" : value.toFixed(digits);
}

function formatTimestamp(timestamp: string | null) {
  if (!timestamp) return "—";
  const date = new Date(timestamp);
  return Number.isNaN(date.getTime()) ? timestamp : date.toLocaleString();
}

function anomalyStatus(observation: Observation) {
  if (observation.is_threshold_anomaly && observation.is_ml_anomaly) {
    return "Both";
  }
  if (observation.is_threshold_anomaly) return "Threshold";
  if (observation.is_ml_anomaly) return "ML";
  return "Normal";
}

function statusClass(status: string) {
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

export default function MethanePage() {
  const [observations, setObservations] = useState<Observation[]>([]);
  const [totalObservations, setTotalObservations] = useState<number | null>(
    null
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState(0);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [search, setSearch] = useState("");
  const [anomalyFilter, setAnomalyFilter] = useState(ALL_FILTER);
  const [sourceFilter, setSourceFilter] = useState(ALL_FILTER);
  const [pipelineFilter, setPipelineFilter] = useState(ALL_FILTER);
  const [selectedObservationId, setSelectedObservationId] = useState<
    string | null
  >(null);

  useEffect(() => {
    let cancelled = false;

    fetchAPI<ObservationsResponse>("/api/observations?limit=1000&offset=0")
      .then((result) => {
        if (!cancelled) {
          setObservations(result.observations);
          setTotalObservations(result.total);
          setLastUpdated(new Date());
        }
      })
      .catch((requestError) => {
        if (!cancelled) {
          console.error("Observation API error:", requestError);
          setError("Unable to load methane observations.");
          setObservations([]);
          setTotalObservations(null);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [retryCount]);

  const anomalyOptions = useMemo(
    () => [
      ALL_FILTER,
      "Normal",
      "Threshold",
      "ML",
      "Both",
    ],
    []
  );
  const sourceOptions = useMemo(
    () => [
      ALL_FILTER,
      ...new Set(
        observations
          .map((observation) => observation.source_label)
          .filter((source): source is string => Boolean(source))
      ),
    ],
    [observations]
  );
  const pipelineOptions = useMemo(
    () => [
      ALL_FILTER,
      ...new Set(
        observations
          .map((observation) => observation.pipeline_id)
          .filter((pipelineId): pipelineId is string => Boolean(pipelineId))
      ),
    ],
    [observations]
  );
  const filteredObservations = useMemo(() => {
    const query = search.trim().toLowerCase();

    return observations.filter((observation) => {
      const status = anomalyStatus(observation);
      const matchesSearch =
        observation.observation_id.toLowerCase().includes(query) ||
        (observation.pipeline_id?.toLowerCase().includes(query) ?? false);
      const matchesAnomaly =
        anomalyFilter === ALL_FILTER || anomalyFilter === status;
      const matchesSource =
        sourceFilter === ALL_FILTER || observation.source_label === sourceFilter;
      const matchesPipeline =
        pipelineFilter === ALL_FILTER ||
        observation.pipeline_id === pipelineFilter;
      return matchesSearch && matchesAnomaly && matchesSource && matchesPipeline;
    });
  }, [observations, search, anomalyFilter, sourceFilter, pipelineFilter]);

  const metrics = useMemo(() => {
    const concentrations = observations
      .map((observation) => observation.methane_concentration_ppm)
      .filter((value): value is number => value != null && Number.isFinite(value));

    return {
      average:
        concentrations.length > 0
          ? concentrations.reduce((sum, value) => sum + value, 0) /
            concentrations.length
          : null,
      threshold: observations.filter(
        (observation) => observation.is_threshold_anomaly
      ).length,
      ml: observations.filter((observation) => observation.is_ml_anomaly).length,
    };
  }, [observations]);

  const loadedCount = observations.length;
  const totalCount = totalObservations ?? loadedCount;
  const hasPartialDataset = totalCount > loadedCount;

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
          Methane Observations
        </h3>
        <p className="mt-2 text-sm text-muted">
          Fleet-wide methane readings, anomaly signals and source attribution.
        </p>
        </div>
        <div className="flex items-center gap-3">
          {lastUpdated && <span className="text-xs text-muted">Fetched {lastUpdated.toLocaleTimeString()}</span>}
          <button type="button" onClick={retryConnection} disabled={loading} aria-busy={loading} className="rounded-lg border border-border px-3 py-2 text-xs text-secondary hover:bg-surface-hover disabled:opacity-60">{loading ? "Refreshing…" : "Refresh data"}</button>
        </div>
      </div>

      {loading ? (
        <div className="rounded-xl border border-border bg-surface p-6 text-sm text-muted">
          Loading methane observations...
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
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <SummaryCard
              label="Total Observations"
              value={totalCount.toLocaleString()}
              detail={
                hasPartialDataset
                  ? `${loadedCount.toLocaleString()} most recent records loaded for analysis`
                  : "Readings returned by the fleet endpoint"
              }
              accent="text-foreground"
            />
            <SummaryCard
              label="Average Methane Concentration"
              value={`${formatNumber(metrics.average)} ppm`}
              detail={
                hasPartialDataset
                  ? "Average across loaded records only"
                  : "Average of available concentration values"
              }
              accent="text-success"
            />
            <SummaryCard
              label="Threshold Anomalies"
              value={metrics.threshold.toString()}
              detail={
                hasPartialDataset
                  ? "Loaded records above the threshold rule"
                  : "Readings above the threshold rule"
              }
              accent="text-warning"
            />
            <SummaryCard
              label="ML-Detected Anomalies"
              value={metrics.ml.toString()}
              detail={
                hasPartialDataset
                  ? "Loaded records flagged by the ML detector"
                  : "Readings flagged by the ML detector"
              }
              accent="text-danger"
            />
          </div>

          {observations.length === 0 ? (
            <div className="rounded-xl border border-border bg-surface p-6 text-sm text-muted">
              No methane observations are available.
            </div>
          ) : (
            <>
              <ObservationMap
                observations={observations}
                selectedObservationId={selectedObservationId}
                onObservationSelect={setSelectedObservationId}
              />

              <section className="rounded-xl border border-border bg-surface">
                <div className="border-b border-border p-6">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <h3 className="font-semibold">Observation Directory</h3>
                      <p className="mt-1 text-xs text-muted">
                        Search by observation or associated pipeline ID.
                      </p>
                    </div>
                    <p className="text-xs text-muted">
                      Showing{" "}
                      {filteredObservations.length.toLocaleString()} of{" "}
                      {loadedCount.toLocaleString()} loaded observations
                      {hasPartialDataset
                        ? ` · ${totalCount.toLocaleString()} total available`
                        : ""}
                    </p>
                  </div>
                  <div className="mt-5 flex flex-wrap gap-3">
                    <label className="flex min-w-0 flex-1 flex-col gap-2 text-xs text-muted sm:min-w-56">
                      Search observations
                      <input
                        type="search"
                        value={search}
                        onChange={(event) => setSearch(event.target.value)}
                        placeholder="Observation or pipeline ID"
                        className="rounded-lg border border-border bg-surface-sunken px-3 py-2.5 text-sm text-secondary outline-none placeholder:text-subtle focus:border-accent/60"
                      />
                    </label>
                    <SelectField
                      label="Filter by anomaly status"
                      value={anomalyFilter}
                      options={anomalyOptions}
                      onChange={setAnomalyFilter}
                    />
                    <SelectField
                      label="Filter by source"
                      value={sourceFilter}
                      options={sourceOptions}
                      onChange={setSourceFilter}
                    />
                    <SelectField
                      label="Filter by pipeline"
                      value={pipelineFilter}
                      options={pipelineOptions}
                      onChange={setPipelineFilter}
                    />
                    <button
                      type="button"
                      onClick={() => {
                        setSearch("");
                        setAnomalyFilter(ALL_FILTER);
                        setSourceFilter(ALL_FILTER);
                        setPipelineFilter(ALL_FILTER);
                      }}
                      className="self-end rounded-lg border border-border px-4 py-2.5 text-sm text-secondary transition hover:border-accent/40 hover:text-foreground"
                    >
                      Clear filters
                    </button>
                  </div>
                </div>

                {filteredObservations.length === 0 ? (
                  <div className="p-6 text-sm text-muted">
                    No observations match the selected search and filters.
                  </div>
                ) : (
                  <div className="divide-y divide-border-subtle">
                    {filteredObservations.map((observation) => {
                      const status = anomalyStatus(observation);
                      return (
                        <button
                          key={observation.observation_id}
                          type="button"
                          onClick={() =>
                            setSelectedObservationId(observation.observation_id)
                          }
                          aria-pressed={
                            selectedObservationId === observation.observation_id
                          }
                          className={`grid w-full grid-cols-2 gap-x-4 gap-y-3 px-4 py-4 text-left transition hover:bg-surface-hover sm:px-6 md:grid-cols-3 xl:grid-cols-6 ${
                            selectedObservationId === observation.observation_id
                              ? "bg-accent/5 ring-1 ring-inset ring-accent/30"
                              : ""
                          }`}
                        >
                          <div className="col-span-2 min-w-0 sm:col-span-1">
                            <p className="text-xs text-muted">Observation ID</p>
                            <p className="mt-1 break-all font-medium text-foreground">
                              {observation.observation_id}
                            </p>
                          </div>
                          <div className="col-span-2 min-w-0 sm:col-span-1">
                            <p className="text-xs text-muted">Timestamp</p>
                            <p className="mt-1 break-words text-sm text-secondary">
                              {formatTimestamp(observation.timestamp)}
                            </p>
                          </div>
                          <div className="min-w-0">
                            <p className="text-xs text-muted">Concentration</p>
                            <p className="mt-1 text-sm text-secondary">
                              {formatNumber(
                                observation.methane_concentration_ppm
                              )}{" "}
                              ppm
                            </p>
                          </div>
                          <div className="min-w-0">
                            <p className="text-xs text-muted">Source</p>
                            <p className="mt-1 break-words text-sm text-secondary">
                              {observation.source_label ?? "—"}
                            </p>
                          </div>
                          <div className="min-w-0">
                            <p className="text-xs text-muted">Anomaly Status</p>
                            <p
                              className={`mt-1 flex items-center gap-1.5 text-sm ${statusClass(
                                status
                              )}`}
                            >
                              <span
                                className={`h-1.5 w-1.5 rounded-full ${statusDotClass(
                                  status
                                )}`}
                              />
                              {status}
                            </p>
                          </div>
                          <div className="min-w-0">
                            <p className="text-xs text-muted">Pipeline</p>
                            <p className="mt-1 break-words text-sm text-secondary">
                              {observation.pipeline_id ?? "Unattributed"}
                            </p>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                )}
              </section>
            </>
          )}

          <div className="rounded-xl border border-warning/25 bg-warning/5 p-5">
            <div className="flex items-start gap-3">
              <span className="text-warning">ⓘ</span>
              <div>
                <h4 className="text-sm font-medium text-warning">
                  Simulated Observation Data
                </h4>
                <p className="mt-1 text-xs leading-6 text-muted">
                  This observation dataset is simulated for demonstration and
                  does not represent verified field measurements. Threshold and
                  ML anomaly flags are dataset outputs.
                </p>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
