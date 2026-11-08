"use client";

import { useEffect, useMemo, useState } from "react";
import PipelineMap from "../../src/components/PipelineMap";
import { fetchAPI } from "../../src/lib/api";

interface Pipeline {
  pipeline_id: string;
  type: string;
  status: string;
  material: string;
  pressure_bar: number | null;
  installation_year: number | null;
}

interface PipelinesResponse {
  total: number;
  pipelines: Pipeline[];
}

const ALL_FILTER = "All";

function SummaryCard({
  label,
  value,
  accent,
}: {
  label: string;
  value: number;
  accent: string;
}) {
  return (
    <div className="rounded-xl border border-border bg-surface p-5">
      <p className="text-sm text-muted">{label}</p>
      <p className={`mt-3 text-3xl font-semibold tracking-tight ${accent}`}>
        {value}
      </p>
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

export default function PipelinesPage() {
  const [pipelines, setPipelines] = useState<Pipeline[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState(0);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState(ALL_FILTER);
  const [typeFilter, setTypeFilter] = useState(ALL_FILTER);
  const [selectedPipelineId, setSelectedPipelineId] = useState<string | null>(
    null
  );

  useEffect(() => {
    let cancelled = false;

    fetchAPI<PipelinesResponse>("/api/pipelines")
      .then((result) => {
        if (!cancelled) {
          setPipelines(result.pipelines);
          setLastUpdated(new Date());
        }
      })
      .catch((requestError) => {
        if (!cancelled) {
          console.error("Pipeline directory API error:", requestError);
          setError("Unable to load pipeline records.");
          setPipelines([]);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [retryCount]);

  const statuses = useMemo(
    () => [ALL_FILTER, ...new Set(pipelines.map((pipeline) => pipeline.status))],
    [pipelines]
  );
  const types = useMemo(
    () => [ALL_FILTER, ...new Set(pipelines.map((pipeline) => pipeline.type))],
    [pipelines]
  );
  const filteredPipelines = useMemo(() => {
    const query = search.trim().toLowerCase();

    return pipelines.filter((pipeline) => {
      const matchesSearch = pipeline.pipeline_id.toLowerCase().includes(query);
      const matchesStatus =
        statusFilter === ALL_FILTER || pipeline.status === statusFilter;
      const matchesType =
        typeFilter === ALL_FILTER || pipeline.type === typeFilter;
      return matchesSearch && matchesStatus && matchesType;
    });
  }, [pipelines, search, statusFilter, typeFilter]);

  const counts = useMemo(
    () => ({
      total: pipelines.length,
      active: pipelines.filter((pipeline) => pipeline.status === "Active")
        .length,
      maintenance: pipelines.filter(
        (pipeline) => pipeline.status === "Maintenance"
      ).length,
      leaking: pipelines.filter((pipeline) => pipeline.status === "Leaking")
        .length,
    }),
    [pipelines]
  );

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
          Pipeline Network
        </h3>
        <p className="mt-2 text-sm text-muted">
          Explore registered pipeline routes and operational details.
        </p>
        </div>
        <div className="flex items-center gap-3">
          {lastUpdated && <span className="text-xs text-muted">Fetched {lastUpdated.toLocaleTimeString()}</span>}
          <button type="button" onClick={retryConnection} disabled={loading} aria-busy={loading} className="rounded-lg border border-border px-3 py-2 text-xs text-secondary hover:bg-surface-hover disabled:opacity-60">{loading ? "Refreshing…" : "Refresh data"}</button>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <SummaryCard
          label="Total Pipelines"
          value={counts.total}
          accent="text-foreground"
        />
        <SummaryCard
          label="Active Pipelines"
          value={counts.active}
          accent="text-success"
        />
        <SummaryCard
          label="Maintenance Pipelines"
          value={counts.maintenance}
          accent="text-warning"
        />
        <SummaryCard
          label="Pipelines Marked as Leaking"
          value={counts.leaking}
          accent="text-danger"
        />
      </div>

      <PipelineMap
        selectedPipelineId={selectedPipelineId}
        onPipelineSelect={setSelectedPipelineId}
      />

      <section className="rounded-xl border border-border bg-surface">
        <div className="border-b border-border p-6">
          <h3 className="font-semibold">Pipeline Directory</h3>
          <p className="mt-1 text-xs text-muted">
            Select a pipeline to highlight it on the map.
          </p>

          <div className="mt-5 flex flex-wrap gap-3">
            <label className="flex min-w-0 flex-1 flex-col gap-2 text-xs text-muted sm:min-w-56">
              Search by pipeline ID
              <input
                type="search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="e.g. P-001"
                className="rounded-lg border border-border bg-surface-sunken px-3 py-2.5 text-sm text-secondary outline-none placeholder:text-subtle focus:border-accent/60"
              />
            </label>
            <SelectField
              label="Filter by status"
              value={statusFilter}
              options={statuses}
              onChange={setStatusFilter}
            />
            <SelectField
              label="Filter by type"
              value={typeFilter}
              options={types}
              onChange={setTypeFilter}
            />
          </div>
        </div>

        {loading ? (
          <div className="p-6 text-sm text-muted">
            Loading pipeline records...
          </div>
        ) : error ? (
          <div className="p-6">
            <p className="text-sm text-danger">{error}</p>
            <button
              type="button"
              onClick={retryConnection}
              className="mt-4 rounded-lg border border-danger/30 bg-danger/10 px-4 py-2 text-sm text-danger transition hover:bg-danger/20"
            >
              Retry Connection
            </button>
          </div>
        ) : filteredPipelines.length === 0 ? (
          <div className="p-6 text-sm text-muted">
            {pipelines.length === 0
              ? "No pipeline records are available."
              : "No pipelines match the selected search and filters."}
          </div>
        ) : (
          <div className="divide-y divide-border-subtle">
            {filteredPipelines.map((pipeline) => {
              const statusText =
                pipeline.status === "Active"
                  ? "text-success"
                  : pipeline.status === "Leaking"
                    ? "text-danger"
                    : pipeline.status === "Maintenance"
                      ? "text-warning"
                      : "text-unknown";
              const statusDot =
                pipeline.status === "Active"
                  ? "bg-success"
                  : pipeline.status === "Leaking"
                    ? "bg-danger"
                    : pipeline.status === "Maintenance"
                      ? "bg-warning"
                      : "bg-unknown";

              return (
                <button
                  key={pipeline.pipeline_id}
                  type="button"
                  onClick={() => setSelectedPipelineId(pipeline.pipeline_id)}
                  aria-pressed={selectedPipelineId === pipeline.pipeline_id}
                  className={`grid w-full grid-cols-2 gap-x-4 gap-y-3 px-4 py-4 text-left transition hover:bg-surface-hover sm:px-6 md:grid-cols-3 xl:grid-cols-6 ${
                    selectedPipelineId === pipeline.pipeline_id
                      ? "bg-accent/5 ring-1 ring-inset ring-accent/30"
                      : ""
                  }`}
                >
                  <div className="col-span-2 min-w-0 sm:col-span-1">
                    <p className="text-xs text-muted">Pipeline ID</p>
                    <p className="mt-1 break-all font-medium text-foreground">
                      {pipeline.pipeline_id}
                    </p>
                  </div>
                  <div className="min-w-0">
                    <p className="text-xs text-muted">Type</p>
                    <p className="mt-1 break-words text-sm text-secondary">
                      {pipeline.type}
                    </p>
                  </div>
                  <div className="min-w-0">
                    <p className="text-xs text-muted">Status</p>
                    <p
                      className={`mt-1 flex items-center gap-1.5 text-sm ${statusText}`}
                    >
                      <span
                        className={`h-1.5 w-1.5 rounded-full ${statusDot}`}
                      />
                      {pipeline.status}
                    </p>
                  </div>
                  <div className="min-w-0">
                    <p className="text-xs text-muted">Material</p>
                    <p className="mt-1 break-words text-sm text-secondary">
                      {pipeline.material}
                    </p>
                  </div>
                  <div className="min-w-0">
                    <p className="text-xs text-muted">Pressure</p>
                    <p className="mt-1 text-sm text-secondary">
                      {pipeline.pressure_bar != null
                        ? `${pipeline.pressure_bar} bar`
                        : "—"}
                    </p>
                  </div>
                  <div className="min-w-0">
                    <p className="text-xs text-muted">Installation Year</p>
                    <p className="mt-1 text-sm text-secondary">
                      {pipeline.installation_year ?? "—"}
                    </p>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </section>

      <div className="rounded-xl border border-warning/25 bg-warning/5 p-5">
        <div className="flex items-start gap-3">
          <span className="text-warning">ⓘ</span>
          <div>
            <h4 className="text-sm font-medium text-warning">
              Prototype Data Notice
            </h4>
            <p className="mt-1 text-xs leading-6 text-muted">
              This dashboard currently uses synthetic pipeline and sensor data
              for demonstration. Pipeline status labels should not be
              interpreted as verified field conditions.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
