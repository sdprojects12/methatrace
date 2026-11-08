"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { fetchAPI } from "../src/lib/api";
import PipelineMap from "../src/components/PipelineMap";
import ReportGenerator from "../src/components/ReportGenerator";
interface DashboardData {
  pipeline_total: number;
  status_counts: Record<string, number>;
  type_counts: Record<string, number>;
  observation_total: number;
  threshold_anomalies: number;
  ml_anomalies: number;
  both_methods: number;
  segments_with_methane_anomalies: number;
  unattributed_observations: number;
  sensor_alerts: number;
  high_risk_pipelines: { pipeline_id: string; score: number; level: string }[];
  high_risk_count: number;
}

interface FleetRiskResponse {
  assessments: { pipeline_id: string; score: number | null; level: string; data_quality: string; sensor_alert: boolean }[];
}

function StatCard({
  label,
  value,
  detail,
  accent = "text-foreground",
}: {
  label: string;
  value: string | number;
  detail: string;
  accent?: string;
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

function StatusRow({
  label,
  count,
  total,
  color,
}: {
  label: string;
  count: number;
  total: number;
  color: string;
}) {
  const percentage = total > 0 ? (count / total) * 100 : 0;

  return (
    <div className="space-y-2">
      <div className="flex justify-between text-sm">
        <span className="text-secondary">{label}</span>
        <span className="text-muted">
          {count} <span className="text-subtle">({percentage.toFixed(1)}%)</span>
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-surface-hover">
        <div
          className={`h-full rounded-full ${color}`}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
}

export default function Home() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [retryCount, setRetryCount] = useState(0);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();

    Promise.all([
      fetchAPI<DashboardData>("/api/dashboard/summary", { signal: controller.signal }),
      fetchAPI<FleetRiskResponse>("/api/risk", { signal: controller.signal }),
    ])
      .then(([summary, fleetRisk]) => {
        const validRisks = fleetRisk.assessments.filter(
          (risk): risk is typeof risk & { score: number } =>
            risk.score != null && Number.isFinite(risk.score) &&
            risk.data_quality === "complete" && risk.level !== "Incomplete"
        );
        const highRiskCount = validRisks.filter(
          (risk) => risk.level.toLowerCase() === "high"
        ).length;
        const topRisks = [...validRisks]
          .sort((a, b) => b.score - a.score)
          .slice(0, 3);
        const result = {
          ...summary,
          sensor_alerts: fleetRisk.assessments.filter((risk) => risk.sensor_alert).length,
          high_risk_count: highRiskCount,
          high_risk_pipelines: topRisks,
        };
        if (!cancelled) {
          setData(result);
          setLastUpdated(new Date());
        }
      })
      .catch((error) => {
        if (!cancelled) {
          console.error("Dashboard API error:", error);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

     return () => {
        cancelled = true;
        controller.abort();
      };
  }, [retryCount]);

  const retryConnection = () => {
    setData(null);
    setLoading(true);
    setRetryCount((count) => count + 1);
  };

  const apiStatus = loading
    ? {
        label: "Connecting...",
        className: "border-warning/25 bg-warning/10 text-warning",
        dotClassName: "bg-warning",
      }
    : data
      ? {
          label: "API Connected",
          className: "border-success/25 bg-success/10 text-success",
          dotClassName: "bg-success",
        }
      : {
          label: "Disconnected",
          className: "border-danger/25 bg-danger/10 text-danger",
          dotClassName: "bg-danger",
        };

  const active = data?.status_counts?.Active ?? 0;
  const maintenance = data?.status_counts?.Maintenance ?? 0;
  const leaking = data?.status_counts?.Leaking ?? 0;
  const total = data?.pipeline_total ?? 0;

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-end gap-3">
        {lastUpdated && <span className="text-xs text-muted">Updated {lastUpdated.toLocaleTimeString()}</span>}
        <button type="button" onClick={retryConnection} disabled={loading} aria-busy={loading}
          className="rounded-lg border border-border px-3 py-2 text-xs text-secondary hover:bg-surface-hover disabled:opacity-60">
          {loading ? "Refreshing…" : "Refresh data"}
        </button>
        <span
          className={`flex items-center gap-2 rounded-full border px-3 py-2 text-xs ${apiStatus.className}`}
        >
          <span className={`h-2 w-2 rounded-full ${apiStatus.dotClassName}`} />
          {apiStatus.label}
        </span>
      </div>

      {/* Introduction */}
      <div>
        <h3 className="text-2xl font-semibold tracking-tight">
          Network Overview
        </h3>
        <p className="mt-2 text-sm text-muted">
          Pipeline infrastructure and methane observation summary.
        </p>
      </div>

      {loading ? (
        <div className="rounded-xl border border-border bg-surface p-6 text-muted">
          Loading dashboard data...
        </div>
      ) : !data ? (
            <div className="rounded-xl border border-danger/25 bg-danger/5 p-6">
              <h3 className="font-medium text-danger">
                Unable to load dashboard data
              </h3>
              <p className="mt-2 text-sm text-muted">
                Check that the FastAPI backend is running at the configured API URL.
              </p>
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
              {/* Primary statistics */}
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                {[
                  { label: "Leaking Pipelines", value: leaking, detail: "Marked as leaking", href: "/pipelines", accent: "text-danger" },
                  { label: "High Risk Pipelines", value: data.high_risk_count, detail: "Simulated risk assessments", href: "/risk", accent: "text-warning" },
                  { label: "Active Sensor Alerts", value: data.sensor_alerts, detail: "Current simulated alerts", href: "/sensors", accent: "text-danger" },
                  { label: "Methane Anomalies", value: data.threshold_anomalies + data.ml_anomalies - data.both_methods, detail: "Unique flagged observations", href: "/methane", accent: "text-warning" },
                ].map((item) => <Link key={item.label} href={item.href} className="block rounded-xl focus-visible:outline-offset-4">
                  <StatCard label={item.label} value={item.value} detail={item.detail} accent={item.accent} />
                </Link>)}
              </div>

              <section className="rounded-xl border border-border bg-surface p-5">
                <h3 className="font-semibold">Top Risk Pipelines</h3>
                <p className="mt-1 text-xs text-muted">Highest available simulated risk scores</p>
                {data.high_risk_pipelines.length ? <div className="mt-4 divide-y divide-border-subtle">
                  {data.high_risk_pipelines.map((pipeline) => <Link key={pipeline.pipeline_id} href={`/risk?pipeline=${encodeURIComponent(pipeline.pipeline_id)}`} className="flex flex-wrap items-center justify-between gap-2 py-3 text-sm hover:text-accent">
                    <span className="break-all font-medium">{pipeline.pipeline_id}</span><span className="text-danger">{pipeline.level} · {pipeline.score.toFixed(1)}</span>
                  </Link>)}
                </div> : <p className="mt-4 text-sm text-muted">No pipeline risk assessments are available.</p>}
              </section>

              {/* Secondary statistics */}
              <div className="grid gap-4 sm:grid-cols-3">
                <StatCard label="Total Pipelines" value={data.pipeline_total} detail="Registered pipeline records" />
                <StatCard label="Methane Observations" value={data.observation_total} detail="Available observation records" />
                <StatCard label="ML Anomalies" value={data.ml_anomalies} detail="Flagged by Isolation Forest" accent="text-warning" />
                <StatCard
                  label="Threshold Anomalies"
                  value={data.threshold_anomalies}
                  detail="Flagged by the concentration threshold"
                  accent="text-warning"
                />
                <StatCard
                  label="Both Detection Methods"
                  value={data.both_methods}
                  detail="Flagged by both methods"
                  accent="text-success"
                />
                <StatCard
                  label="Unattributed Observations"
                  value={data.unattributed_observations}
                  detail="Not assigned to a pipeline segment"
                />
              </div>
              {/* Pipeline map */}
              <PipelineMap />

              <ReportGenerator />

              {/* Detailed panels */}
              <div className="grid gap-6 xl:grid-cols-2">
                <div className="rounded-xl border border-border bg-surface p-6">
                  <div className="mb-6">
                    <h3 className="font-semibold">Pipeline Status</h3>
                    <p className="mt-1 text-xs text-muted">
                      Distribution across registered pipelines
                    </p>
                  </div>

                  <div className="space-y-6">
                    <StatusRow
                      label="Active"
                      count={active}
                      total={total}
                      color="bg-success"
                    />
                    <StatusRow
                      label="Maintenance"
                      count={maintenance}
                      total={total}
                      color="bg-warning"
                    />
                    <StatusRow
                      label="Marked as Leaking"
                      count={leaking}
                      total={total}
                      color="bg-danger"
                    />
                  </div>

                  <div className="mt-8 border-t border-border pt-5">
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-muted">
                        Total pipelines
                      </span>
                      <span className="text-lg font-semibold">{total}</span>
                    </div>
                  </div>
                </div>

                <div className="rounded-xl border border-border bg-surface p-6">
                  <div className="mb-6">
                    <h3 className="font-semibold">Pipeline Categories</h3>
                    <p className="mt-1 text-xs text-muted">
                      Breakdown by infrastructure type
                    </p>
                  </div>

                  <div className="space-y-5">
                    {Object.entries(data.type_counts || {}).map(
                      ([type, count]) => (
                        <StatusRow
                          key={type}
                          label={type}
                          count={count}
                          total={total}
                          color="bg-info"
                        />
                      )
                    )}
                  </div>
                </div>
              </div>

              {/* Dataset notice */}
              <div className="rounded-xl border border-warning/25 bg-warning/5 p-5">
                <div className="flex items-start gap-3">
                  <span className="text-warning">ⓘ</span>
                  <div>
                    <h4 className="text-sm font-medium text-warning">
                      Prototype Data Notice
                    </h4>
                    <p className="mt-1 text-xs leading-6 text-muted">
                      This dashboard currently uses synthetic pipeline and
                      sensor data for demonstration. Anomaly flags and
                      pipeline status labels are dataset outputs and should
                      not be interpreted as verified field conditions.
                    </p>
                  </div>
                </div>
              </div>
        </>
      )}
    </div>
  );
}
