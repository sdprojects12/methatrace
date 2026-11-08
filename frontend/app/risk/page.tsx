"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { fetchAPI } from "../../src/lib/api";

interface Pipeline {
  pipeline_id: string;
  type: string;
  status: string;
  material: string;
  pressure_bar: number | null;
  installation_year: number | null;
}

interface PipelineResponse {
  total: number;
  pipelines: Pipeline[];
}

interface RiskFactor {
  name: string;
  score: number | null;
  maximum: number | null;
  available: boolean;
  explanation: string;
}

interface RiskSignals {
  operational_status: string | null;
  sensor_status: string | null;
  sensor_alert: boolean;
  threshold_anomalies: number;
  ml_anomalies: number;
  observation_count: number;
}

interface RiskWeather {
  wind_speed_kmh?: number | null;
  wind_direction_deg?: number | null;
  temperature_c?: number | null;
  source?: string | null;
  note?: string | null;
}

interface RiskResponse {
  pipeline_id: string;
  status: string;
  score: number | null;
  level: string | null;
  factors: string[];
  factor_breakdown: RiskFactor[];
  scored_maximum: number | null;
  data_quality: string | null;
  missing_factors: string[];
  signals: RiskSignals;
  weather: RiskWeather;
  simulated: boolean;
  message: string;
  disclaimer: string;
}

const ALL_FILTER = "All";

function formatValue(value: number | null | undefined, suffix = "") {
  return value == null || !Number.isFinite(value) ? "—" : `${value}${suffix}`;
}

function formatRiskScore(value: number | null | undefined) {
  return value == null || !Number.isFinite(value) ? "—" : value.toFixed(1);
}

function riskAccent(level: string | null) {
  if (level === "High") return "text-danger";
  if (level === "Medium") return "text-warning";
  if (level === "Low") return "text-success";
  return "text-secondary";
}

function riskBar(level: string | null) {
  if (level === "High") return "bg-danger";
  if (level === "Medium") return "bg-warning";
  if (level === "Low") return "bg-success";
  return "bg-unknown";
}

function statusAccent(status: string | null) {
  if (status === "Leaking" || status?.startsWith("CRITICAL")) {
    return "text-danger";
  }
  if (status === "Maintenance") return "text-warning";
  if (status === "Active" || status === "NORMAL") return "text-success";
  return "text-secondary";
}

function InfoRow({
  label,
  value,
  valueClassName = "text-secondary",
}: {
  label: string;
  value: string;
  valueClassName?: string;
}) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-border-subtle py-3 last:border-0">
      <span className="text-sm text-muted">{label}</span>
      <span className={`text-right text-sm ${valueClassName}`}>{value}</span>
    </div>
  );
}

export default function RiskPage() {
  return (
    <Suspense fallback={<div className="rounded-xl border border-border bg-surface p-6 text-sm text-muted">Loading risk analysis...</div>}>
      <RiskAnalysisPage />
    </Suspense>
  );
}

function RiskAnalysisPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const urlPipelineId = searchParams.get("pipeline");
  const [pipelines, setPipelines] = useState<Pipeline[]>([]);
  const [pipelineLoading, setPipelineLoading] = useState(true);
  const [pipelineError, setPipelineError] = useState<string | null>(null);
  const [pipelineRetryCount, setPipelineRetryCount] = useState(0);
  const [pipelineSearch, setPipelineSearch] = useState("");
  const [pipelineStatusFilter, setPipelineStatusFilter] =
    useState(ALL_FILTER);
  const [pipelineTypeFilter, setPipelineTypeFilter] = useState(ALL_FILTER);
  const [selectedPipelineId, setSelectedPipelineId] = useState<string | null>(
    null
  );
  const selectedPipelineIdRef = useRef<string | null>(null);
  const [risk, setRisk] = useState<RiskResponse | null>(null);
  const [riskLoading, setRiskLoading] = useState(false);
  const [riskError, setRiskError] = useState<string | null>(null);
  const [riskRetryCount, setRiskRetryCount] = useState(0);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  useEffect(() => {
    let cancelled = false;

    fetchAPI<PipelineResponse>("/api/pipelines")
      .then((result) => {
        if (!cancelled) {
          setPipelines(result.pipelines);
        }
      })
      .catch((requestError) => {
        if (!cancelled) {
          console.error("Risk pipeline API error:", requestError);
          setPipelineError("Unable to load pipelines for risk analysis.");
          setPipelines([]);
        }
      })
      .finally(() => {
        if (!cancelled) setPipelineLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [pipelineRetryCount]);

  useEffect(() => {
    if (pipelineLoading) return;
    const requestedPipeline = urlPipelineId
      ? pipelines.find((pipeline) => pipeline.pipeline_id === urlPipelineId)
      : undefined;
    const nextPipelineId = requestedPipeline?.pipeline_id ?? pipelines[0]?.pipeline_id ?? null;
    if (urlPipelineId && !requestedPipeline) {
      router.replace("/risk", { scroll: false });
    }
    if (selectedPipelineIdRef.current !== nextPipelineId) {
      selectedPipelineIdRef.current = nextPipelineId;
      setSelectedPipelineId(nextPipelineId);
      setRisk(null);
      setRiskError(null);
      setRiskLoading(Boolean(nextPipelineId));
      setRiskRetryCount(0);
    }
  }, [pipelineLoading, pipelines, urlPipelineId, router]);

  useEffect(() => {
    if (!selectedPipelineId) return;

    let cancelled = false;

    fetchAPI<RiskResponse>(
      `/api/risk/${encodeURIComponent(selectedPipelineId)}`
    )
      .then((result) => {
        if (!cancelled) { setRisk(result); setLastUpdated(new Date()); }
      })
      .catch((requestError) => {
        if (!cancelled) {
          console.error(
            `Risk API error for ${selectedPipelineId}:`,
            requestError
          );
          setRiskError("Unable to load the risk assessment.");
        }
      })
      .finally(() => {
        if (!cancelled) setRiskLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedPipelineId, riskRetryCount]);

  const filteredPipelines = useMemo(() => {
    const query = pipelineSearch.trim().toLowerCase();
    return pipelines.filter((pipeline) => {
      const matchesSearch = pipeline.pipeline_id.toLowerCase().includes(query);
      const matchesStatus =
        pipelineStatusFilter === ALL_FILTER ||
        pipeline.status === pipelineStatusFilter;
      const matchesType =
        pipelineTypeFilter === ALL_FILTER ||
        pipeline.type === pipelineTypeFilter;
      return matchesSearch && matchesStatus && matchesType;
    });
  }, [pipelines, pipelineSearch, pipelineStatusFilter, pipelineTypeFilter]);

  const pipelineStatusOptions = useMemo(
    () => [
      ALL_FILTER,
      ...new Set(pipelines.map((pipeline) => pipeline.status)),
    ],
    [pipelines]
  );
  const pipelineTypeOptions = useMemo(
    () => [ALL_FILTER, ...new Set(pipelines.map((pipeline) => pipeline.type))],
    [pipelines]
  );

  const selectedPipeline = pipelines.find(
    (pipeline) => pipeline.pipeline_id === selectedPipelineId
  );

  const retryPipelines = () => {
    setPipelineLoading(true);
    setPipelineError(null);
    setPipelineRetryCount((count) => count + 1);
  };

  const retryRisk = () => {
    setRiskLoading(true);
    setRiskError(null);
    setRiskRetryCount((count) => count + 1);
  };

  const isIncomplete = risk?.level === "Incomplete";
  const scoreMaximum = isIncomplete ? risk.scored_maximum : 100;
  const scorePercentage =
    risk?.score != null && scoreMaximum != null && scoreMaximum > 0
      ? (risk.score / scoreMaximum) * 100
      : 0;

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
        <h3 className="text-2xl font-semibold tracking-tight">Risk Analysis</h3>
        <p className="mt-2 text-sm text-muted">
          Explainable, rule-based indicators for monitored pipeline segments.
        </p>
        </div>
        <div className="flex items-center gap-3">
          {lastUpdated && <span className="text-xs text-muted">Fetched {lastUpdated.toLocaleTimeString()}</span>}
          <button type="button" onClick={() => { retryPipelines(); if (selectedPipelineId) retryRisk(); }} disabled={pipelineLoading || riskLoading} aria-busy={pipelineLoading || riskLoading} className="rounded-lg border border-border px-3 py-2 text-xs text-secondary hover:bg-surface-hover disabled:opacity-60">{pipelineLoading || riskLoading ? "Refreshing…" : "Refresh data"}</button>
        </div>
      </div>

      {pipelineLoading ? (
        <div className="rounded-xl border border-border bg-surface p-6 text-sm text-muted">
          Loading pipelines...
        </div>
      ) : pipelineError ? (
        <div className="rounded-xl border border-danger/25 bg-danger/5 p-6">
          <p className="text-sm text-danger">{pipelineError}</p>
          <button
            type="button"
            onClick={retryPipelines}
            className="mt-4 rounded-lg border border-danger/30 bg-danger/10 px-4 py-2 text-sm text-danger transition hover:bg-danger/20"
          >
            Retry Connection
          </button>
        </div>
      ) : pipelines.length === 0 ? (
        <div className="rounded-xl border border-border bg-surface p-6 text-sm text-muted">
          No pipelines are available for risk analysis.
        </div>
      ) : (
        <>
          <section className="rounded-xl border border-border bg-surface p-6">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <h3 className="font-semibold">Select Pipeline</h3>
                <p className="mt-1 text-xs text-muted">
                  Choose a pipeline to load its backend risk assessment.
                </p>
              </div>
              {selectedPipeline && (
                <span className="rounded-full border border-accent/25 bg-accent/10 px-3 py-2 text-xs text-success">
                  Selected: {selectedPipeline.pipeline_id}
                </span>
              )}
            </div>

            <input
              type="search"
              value={pipelineSearch}
              onChange={(event) => setPipelineSearch(event.target.value)}
              placeholder="Search by pipeline ID"
              className="mt-5 w-full rounded-lg border border-border bg-surface-sunken px-3 py-2.5 text-sm text-secondary outline-none placeholder:text-subtle focus:border-accent/60"
            />

            <div className="mt-3 flex flex-wrap items-end gap-3">
              <label className="flex min-w-44 flex-1 flex-col gap-2 text-xs text-muted">
                Filter by status
                <select
                  value={pipelineStatusFilter}
                  onChange={(event) =>
                    setPipelineStatusFilter(event.target.value)
                  }
                  className="rounded-lg border border-border bg-surface-sunken px-3 py-2.5 text-sm text-secondary outline-none focus:border-accent/60"
                >
                  {pipelineStatusOptions.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex min-w-44 flex-1 flex-col gap-2 text-xs text-muted">
                Filter by type
                <select
                  value={pipelineTypeFilter}
                  onChange={(event) => setPipelineTypeFilter(event.target.value)}
                  className="rounded-lg border border-border bg-surface-sunken px-3 py-2.5 text-sm text-secondary outline-none focus:border-accent/60"
                >
                  {pipelineTypeOptions.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                onClick={() => {
                  setPipelineSearch("");
                  setPipelineStatusFilter(ALL_FILTER);
                  setPipelineTypeFilter(ALL_FILTER);
                }}
                className="rounded-lg border border-border px-4 py-2.5 text-sm text-secondary transition hover:border-accent/40 hover:text-foreground"
              >
                Clear filters
              </button>
            </div>

            <div className="mt-4 grid max-h-64 gap-2 overflow-y-auto sm:grid-cols-2 lg:grid-cols-3">
              {filteredPipelines.length === 0 ? (
                <p className="text-sm text-muted">
                  No pipelines match your search.
                </p>
              ) : (
                filteredPipelines.map((pipeline) => (
                  <button
                    key={pipeline.pipeline_id}
                    type="button"
                    onClick={() => {
                  router.push(`/risk?pipeline=${encodeURIComponent(pipeline.pipeline_id)}`, { scroll: false });
                      setRisk(null);
                      setRiskError(null);
                      setRiskLoading(true);
                      selectedPipelineIdRef.current = pipeline.pipeline_id;
                      setSelectedPipelineId(pipeline.pipeline_id);
                      setRiskRetryCount(0);
                    }}
                    className={`rounded-lg border p-3 text-left transition ${
                      selectedPipelineId === pipeline.pipeline_id
                        ? "border-accent/40 bg-accent/10"
                        : "border-border bg-surface-sunken hover:bg-surface-hover"
                    }`}
                  >
                    <p className="font-medium text-foreground">
                      {pipeline.pipeline_id}
                    </p>
                    <p className="mt-1 text-xs text-muted">
                      {pipeline.type} · {pipeline.material}
                    </p>
                    <p className={`mt-2 text-xs ${statusAccent(pipeline.status)}`}>
                      {pipeline.status}
                    </p>
                  </button>
                ))
              )}
            </div>
          </section>

          {riskLoading ? (
            <div className="rounded-xl border border-border bg-surface p-6 text-sm text-muted">
              Loading risk assessment for {selectedPipelineId}...
            </div>
          ) : riskError ? (
            <div className="rounded-xl border border-danger/25 bg-danger/5 p-6">
              <p className="text-sm text-danger">{riskError}</p>
              <button
                type="button"
                onClick={retryRisk}
                className="mt-4 rounded-lg border border-danger/30 bg-danger/10 px-4 py-2 text-sm text-danger transition hover:bg-danger/20"
              >
                Retry Assessment
              </button>
            </div>
          ) : !risk ? (
            <div className="rounded-xl border border-border bg-surface p-6 text-sm text-muted">
              Select a pipeline to view its risk assessment.
            </div>
          ) : risk.status !== "ok" ? (
            <div className="rounded-xl border border-warning/25 bg-warning/5 p-6">
              <h3 className="font-medium text-warning">
                Risk engine unavailable
              </h3>
              <p className="mt-2 text-sm text-muted">
                {risk.message || "No risk score is available for this pipeline."}
              </p>
              <button
                type="button"
                onClick={retryRisk}
                className="mt-4 rounded-lg border border-warning/30 bg-warning/10 px-4 py-2 text-sm text-warning transition hover:bg-warning/20"
              >
                Retry Assessment
              </button>
            </div>
          ) : (
            <>
              <section className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
                <div className="rounded-xl border border-border bg-surface p-6">
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                      <p className="text-xs uppercase tracking-widest text-muted">
                        Simulated risk assessment
                      </p>
                      <h3 className="mt-1 text-xl font-semibold">
                        {risk.pipeline_id}
                      </h3>
                    </div>
                    <span
                      className={`text-lg font-semibold ${
                        isIncomplete
                          ? "text-secondary"
                          : riskAccent(risk.level)
                      }`}
                    >
                      {isIncomplete ? "Incomplete" : risk.level ?? "Unavailable"}
                    </span>
                  </div>
                  <div className="mt-8 flex items-end gap-3">
                    <span
                      className={`text-6xl font-semibold tracking-tight ${
                        isIncomplete ? "text-secondary" : riskAccent(risk.level)
                      }`}
                    >
                      {formatRiskScore(risk.score)}
                    </span>
                    <span className="pb-2 text-sm text-muted">
                      / {formatValue(scoreMaximum)}
                    </span>
                  </div>
                  <div className="mt-5 h-3 overflow-hidden rounded-full bg-surface-hover">
                    <div
                      className={`h-full rounded-full ${riskBar(risk.level)}`}
                      style={{
                        width: `${Math.min(100, Math.max(0, scorePercentage))}%`,
                      }}
                    />
                  </div>
                  <div
                    className={`mt-5 rounded-lg border p-4 ${
                      isIncomplete
                        ? "border-warning/25 bg-warning/5"
                        : "border-border-subtle bg-surface-sunken"
                    }`}
                  >
                    <p className="text-sm leading-6 text-muted">
                      {isIncomplete
                        ? "This partial assessment could not evaluate every component. Low, Medium and High thresholds do not apply."
                        : risk.factors?.[risk.factors.length - 1] ||
                          "Assessment completed using the backend rule-based model."}
                    </p>
                    <div className="mt-3 flex flex-wrap gap-3 text-xs text-muted">
                      <span>
                        Scored maximum: {formatValue(risk.scored_maximum)}
                      </span>
                      <span>
                        Data quality:{" "}
                        <span className={isIncomplete ? "text-warning" : "text-success"}>
                          {risk.data_quality ?? "—"}
                        </span>
                      </span>
                    </div>
                    {isIncomplete && risk.missing_factors.length > 0 && (
                      <p className="mt-2 text-xs text-warning">
                        Missing: {risk.missing_factors.join(", ")}
                      </p>
                    )}
                  </div>
                </div>

                <div className="rounded-xl border border-border bg-surface p-6">
                  <h3 className="font-semibold">Selected Pipeline</h3>
                  {selectedPipeline && (
                    <div className="mt-4">
                      <InfoRow label="Pipeline ID" value={selectedPipeline.pipeline_id} />
                      <InfoRow label="Type" value={selectedPipeline.type} />
                      <InfoRow
                        label="Operational status"
                        value={selectedPipeline.status}
                        valueClassName={statusAccent(selectedPipeline.status)}
                      />
                      <InfoRow label="Material" value={selectedPipeline.material} />
                      <InfoRow
                        label="Rated pressure"
                        value={formatValue(selectedPipeline.pressure_bar, " bar")}
                      />
                      <InfoRow
                        label="Installation year"
                        value={formatValue(selectedPipeline.installation_year)}
                      />
                    </div>
                  )}
                </div>
              </section>

              <section className="rounded-xl border border-border bg-surface p-6">
                <h3 className="font-semibold">Score Breakdown</h3>
                <p className="mt-1 text-xs text-muted">
                  Contributions are calculated by the backend; the frontend does not recalculate them.
                </p>
                <div className="mt-6 grid gap-6 lg:grid-cols-2">
                  {risk.factor_breakdown.map((factor) => {
                    const percentage =
                      factor.available &&
                      factor.score != null &&
                      factor.maximum != null &&
                      factor.maximum > 0
                        ? (factor.score / factor.maximum) * 100
                        : 0;
                    return (
                      <div key={factor.name} className="rounded-lg border border-border bg-surface-sunken p-4">
                        <div className="flex items-center justify-between gap-4">
                          <span className="font-medium">{factor.name}</span>
                          <span
                            className={`text-sm ${
                              factor.available ? "text-secondary" : "text-muted"
                            }`}
                          >
                            {factor.available && factor.score != null
                              ? formatRiskScore(factor.score)
                              : "Unavailable"}{" "}
                            / {formatValue(factor.maximum)}
                          </span>
                        </div>
                        <div className="mt-3 h-2 overflow-hidden rounded-full bg-surface-hover">
                          <div
                            className={`h-full rounded-full ${
                              factor.available ? "bg-success" : "bg-unknown"
                            }`}
                            style={{ width: `${Math.min(100, Math.max(0, percentage))}%` }}
                          />
                        </div>
                        <p className="mt-2 text-xs text-muted">
                          {factor.available ? "Evaluated" : "Unavailable"}
                        </p>
                        <p className="mt-3 text-xs leading-5 text-muted">
                          {factor.explanation || "No explanation available."}
                        </p>
                      </div>
                    );
                  })}
                </div>
              </section>

              <section className="grid gap-6 lg:grid-cols-2">
                <div className="rounded-xl border border-border bg-surface p-6">
                  <h3 className="font-semibold">Independent Signals</h3>
                  <p className="mt-1 text-xs text-muted">
                    Operational, methane and simulated telemetry signals remain separate.
                  </p>
                  <div className="mt-4">
                    <InfoRow
                      label="Operational status"
                      value={risk.signals.operational_status ?? "—"}
                      valueClassName={statusAccent(risk.signals.operational_status)}
                    />
                    <InfoRow
                      label="Observation count"
                      value={String(risk.signals.observation_count ?? "—")}
                    />
                    <InfoRow
                      label="Threshold anomalies"
                      value={String(risk.signals.threshold_anomalies ?? "—")}
                      valueClassName={risk.signals.threshold_anomalies > 0 ? "text-warning" : undefined}
                    />
                    <InfoRow
                      label="ML anomalies"
                      value={String(risk.signals.ml_anomalies ?? "—")}
                      valueClassName={risk.signals.ml_anomalies > 0 ? "text-danger" : undefined}
                    />
                    <InfoRow
                      label="Sensor status"
                      value={risk.signals.sensor_status ?? "—"}
                      valueClassName={statusAccent(risk.signals.sensor_status)}
                    />
                    <InfoRow
                      label="Sensor alert"
                      value={risk.signals.sensor_alert ? "Active" : "Inactive"}
                      valueClassName={risk.signals.sensor_alert ? "text-danger" : "text-success"}
                    />
                  </div>
                </div>

                <div className="rounded-xl border border-border bg-surface p-6">
                  <h3 className="font-semibold">Weather Context</h3>
                  <p className="mt-1 text-xs text-muted">
                    Weather values supplied to the backend risk calculation.
                  </p>
                  <div className="mt-4">
                    <InfoRow label="Wind speed" value={formatValue(risk.weather?.wind_speed_kmh, " km/h")} />
                    <InfoRow label="Wind direction" value={formatValue(risk.weather?.wind_direction_deg, "°")} />
                    <InfoRow label="Temperature" value={formatValue(risk.weather?.temperature_c, "°C")} />
                    <InfoRow
                      label="Source"
                      value={risk.weather?.source ?? "—"}
                      valueClassName={
                        risk.weather?.source === "fallback_mock"
                          ? "text-warning"
                          : "text-secondary"
                      }
                    />
                  </div>
                  {risk.weather?.note && (
                    <p className="mt-4 text-xs leading-5 text-warning">
                      {risk.weather.note}
                    </p>
                  )}
                </div>
              </section>

              <div className="rounded-xl border border-warning/25 bg-warning/5 p-5">
                <h4 className="text-sm font-medium text-warning">
                  Simulated Risk Disclaimer
                </h4>
                <p className="mt-1 text-xs leading-6 text-muted">
                  {risk.disclaimer ||
                    "This is a simulated prototype indicator, not a calibrated real-world failure probability or safety assessment."}
                </p>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
