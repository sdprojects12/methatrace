"use client";

import { useEffect, useId, useState } from "react";
import { fetchAPI } from "../lib/api";
import { useReportDownload } from "../lib/useReportDownload";

interface PipelineOption {
  pipeline_id: string;
  type: string;
  status: string;
}

interface PipelinesResponse {
  total: number;
  pipelines: PipelineOption[];
}

export default function ReportGenerator({
  className = "",
}: {
  className?: string;
}) {
  const selectId = useId();
  const [pipelines, setPipelines] = useState<PipelineOption[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState(0);
  const { generating, error, downloaded, download, reset } =
    useReportDownload();

  useEffect(() => {
    let cancelled = false;

    fetchAPI<PipelinesResponse>("/api/pipelines")
      .then((response) => {
        if (cancelled) return;
        setPipelines(response.pipelines);
        setSelectedId((current) =>
          response.pipelines.some(
            (pipeline) => pipeline.pipeline_id === current
          )
            ? current
            : response.pipelines[0]?.pipeline_id ?? ""
        );
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        setLoadError(
          cause instanceof Error
            ? cause.message
            : "Unable to load pipelines."
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [retryCount]);

  const selected = pipelines.find(
    (pipeline) => pipeline.pipeline_id === selectedId
  );

  const handleGenerate = () => {
    if (!selectedId) return;
    void download(selectedId);
  };

  return (
    <section
      id="generate-report"
      className={`rounded-xl border border-border bg-surface p-5 ${className}`}
    >
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          <h3 className="font-semibold">Generate Pipeline Report</h3>
          <p className="mt-1 text-xs text-muted">
            Export the selected pipeline&apos;s operational, methane, sensor,
            and risk data as a PDF.
          </p>
        </div>

        {loading ? (
          <p className="text-sm text-muted">Loading pipelines...</p>
        ) : loadError ? (
          <div className="flex flex-col gap-2 rounded-lg border border-danger/25 bg-danger/5 p-3 text-xs text-danger sm:flex-row sm:items-center">
            <span>{loadError}</span>
            <button
              type="button"
              onClick={() => {
                setLoading(true);
                setLoadError(null);
                setRetryCount((count) => count + 1);
              }}
              className="self-start text-danger underline underline-offset-4 sm:self-auto"
            >
              Retry
            </button>
          </div>
        ) : pipelines.length === 0 ? (
          <p className="text-sm text-muted">No pipelines available.</p>
        ) : (
          <div className="flex w-full flex-col gap-3 sm:flex-row sm:items-end lg:w-auto">
            <label
              htmlFor={selectId}
              className="flex min-w-0 flex-1 flex-col gap-2 text-xs text-muted lg:w-64 lg:flex-none"
            >
              Pipeline
              <select
                id={selectId}
                value={selectedId}
                disabled={generating}
                onChange={(event) => {
                  setSelectedId(event.target.value);
                  reset();
                }}
                className="w-full rounded-lg border border-border bg-surface-sunken px-3 py-2.5 text-sm text-secondary outline-none focus:border-accent/60 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {pipelines.map((pipeline) => (
                  <option key={pipeline.pipeline_id} value={pipeline.pipeline_id}>
                    {pipeline.pipeline_id} · {pipeline.type} · {pipeline.status}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              disabled={generating || !selectedId}
              onClick={handleGenerate}
              className="rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-accent-contrast transition hover:bg-accent-strong disabled:cursor-not-allowed disabled:opacity-50"
            >
              {generating ? "Generating PDF..." : "Download PDF Report"}
            </button>
          </div>
        )}
      </div>

      <div aria-live="polite" className="mt-3 space-y-1">
        {downloaded && (
          <p className="text-xs text-success">
            Report downloaded for {downloaded}.
          </p>
        )}
        {error && (
          <p className="text-xs text-danger">Unable to generate report. {error}</p>
        )}
        {selected && !loading && !loadError && (
          <p className="text-xs text-muted">
            Report includes simulated prototype data only.
          </p>
        )}
      </div>
    </section>
  );
}
