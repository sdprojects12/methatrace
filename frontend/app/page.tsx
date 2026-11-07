"use client";

import { useEffect, useState } from "react";
import { fetchAPI } from "../src/lib/api";

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
}

async function getDashboardData(): Promise<DashboardData | null> {
  try {
    return await fetchAPI<DashboardData>("/api/dashboard/summary");
  } catch (error) {
    console.error("Dashboard API error:", error);
    return null;
  }
}

function StatCard({
  label,
  value,
  detail,
  accent = "text-white",
}: {
  label: string;
  value: string | number;
  detail: string;
  accent?: string;
}) {
  return (
    <div className="rounded-xl border border-white/10 bg-[#151a20] p-5">
      <p className="text-sm text-gray-400">{label}</p>
      <p className={`mt-3 text-3xl font-semibold tracking-tight ${accent}`}>
        {value}
      </p>
      <p className="mt-2 text-xs text-gray-500">{detail}</p>
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
        <span className="text-gray-300">{label}</span>
        <span className="text-gray-400">
          {count} <span className="text-gray-600">({percentage.toFixed(1)}%)</span>
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-white/5">
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

  useEffect(() => {
    getDashboardData()
      .then(setData)
      .finally(() => setLoading(false));
  }, []);

  const active = data?.status_counts?.Active ?? 0;
  const maintenance = data?.status_counts?.Maintenance ?? 0;
  const leaking = data?.status_counts?.Leaking ?? 0;
  const total = data?.pipeline_total ?? 0;

  return (
    <main className="flex min-h-screen bg-[#0d1117] text-white">
      {/* Sidebar */}
      <aside className="hidden w-64 shrink-0 border-r border-white/10 bg-[#11161d] p-6 lg:flex lg:flex-col">
        <div className="mb-12">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-500/15 text-emerald-400">
              <span className="text-xl">M</span>
            </div>
            <div>
              <h1 className="font-semibold tracking-wide">MethaTrace</h1>
              <p className="text-xs text-gray-500">Methane Intelligence</p>
            </div>
          </div>
        </div>

        <p className="mb-4 text-xs font-semibold uppercase tracking-widest text-gray-600">
          Workspace
        </p>

        <nav className="space-y-2 text-sm">
          <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/10 px-4 py-3 text-emerald-400">
            Overview
          </div>
          <div className="rounded-lg px-4 py-3 text-gray-400">
            Pipeline Network
          </div>
          <div className="rounded-lg px-4 py-3 text-gray-400">
            Methane Observations
          </div>
          <div className="rounded-lg px-4 py-3 text-gray-400">
            Sensor Monitoring
          </div>
          <div className="rounded-lg px-4 py-3 text-gray-400">
            Risk Analysis
          </div>
          <div className="rounded-lg px-4 py-3 text-gray-400">
            Reports
          </div>
        </nav>

        <div className="mt-auto rounded-xl border border-white/10 bg-[#171e26] p-4">
          <p className="text-xs text-gray-500">MONITORING AREA</p>
          <p className="mt-2 font-medium">Chakan Industrial Zone</p>
          <p className="mt-1 text-xs text-gray-500">Maharashtra, India</p>
        </div>
      </aside>

      {/* Main content */}
      <section className="min-w-0 flex-1">
        <header className="flex flex-wrap items-center justify-between gap-4 border-b border-white/10 px-6 py-5 lg:px-10">
          <div>
            <p className="text-xs uppercase tracking-widest text-gray-500">
              Methane Intelligence Platform
            </p>
            <h2 className="mt-1 text-xl font-semibold">Overview Dashboard</h2>
          </div>

          <div className="flex items-center gap-3">
            <span className="flex items-center gap-2 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-400">
              <span className="h-2 w-2 rounded-full bg-emerald-400" />
              API Connected
            </span>
            <span className="rounded-lg border border-white/10 px-3 py-2 text-xs text-gray-400">
              Chakan Zone
            </span>
          </div>
        </header>

        <div className="space-y-8 p-6 lg:p-10">
          {/* Introduction */}
          <div>
            <h3 className="text-2xl font-semibold tracking-tight">
              Network Overview
            </h3>
            <p className="mt-2 text-sm text-gray-400">
              Pipeline infrastructure and methane observation summary.
            </p>
          </div>

            {loading ? (
              <div className="rounded-xl border border-white/10 bg-[#151a20] p-6 text-gray-400">
                Loading dashboard data...
              </div>
            ) : !data ? (
            <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-6">
              <h3 className="font-medium text-red-400">
                Unable to load dashboard data
              </h3>
              <p className="mt-2 text-sm text-gray-400">
                Check that the FastAPI backend is running at the configured API URL.
              </p>
            </div>
          ) : (
            <>
              {/* Primary statistics */}
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                <StatCard
                  label="Total Pipelines"
                  value={data.pipeline_total}
                  detail="Registered pipeline records"
                />
                <StatCard
                  label="Methane Observations"
                  value={data.observation_total}
                  detail="Available observation records"
                />
                <StatCard
                  label="ML Anomalies"
                  value={data.ml_anomalies}
                  detail="Flagged by Isolation Forest"
                  accent="text-amber-400"
                />
                <StatCard
                  label="Affected Segments"
                  value={data.segments_with_methane_anomalies}
                  detail="Segments with methane anomalies"
                  accent="text-orange-400"
                />
              </div>

              {/* Secondary statistics */}
              <div className="grid gap-4 sm:grid-cols-3">
                <StatCard
                  label="Threshold Anomalies"
                  value={data.threshold_anomalies}
                  detail="Flagged by the concentration threshold"
                  accent="text-amber-400"
                />
                <StatCard
                  label="Both Detection Methods"
                  value={data.both_methods}
                  detail="Flagged by both methods"
                  accent="text-emerald-400"
                />
                <StatCard
                  label="Unattributed Observations"
                  value={data.unattributed_observations}
                  detail="Not assigned to a pipeline segment"
                />
              </div>

              {/* Detailed panels */}
              <div className="grid gap-6 xl:grid-cols-2">
                <div className="rounded-xl border border-white/10 bg-[#151a20] p-6">
                  <div className="mb-6">
                    <h3 className="font-semibold">Pipeline Status</h3>
                    <p className="mt-1 text-xs text-gray-500">
                      Distribution across registered pipelines
                    </p>
                  </div>

                  <div className="space-y-6">
                    <StatusRow
                      label="Active"
                      count={active}
                      total={total}
                      color="bg-emerald-400"
                    />
                    <StatusRow
                      label="Maintenance"
                      count={maintenance}
                      total={total}
                      color="bg-amber-400"
                    />
                    <StatusRow
                      label="Marked as Leaking"
                      count={leaking}
                      total={total}
                      color="bg-red-400"
                    />
                  </div>

                  <div className="mt-8 border-t border-white/10 pt-5">
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-gray-400">
                        Total pipelines
                      </span>
                      <span className="text-lg font-semibold">{total}</span>
                    </div>
                  </div>
                </div>

                <div className="rounded-xl border border-white/10 bg-[#151a20] p-6">
                  <div className="mb-6">
                    <h3 className="font-semibold">Pipeline Categories</h3>
                    <p className="mt-1 text-xs text-gray-500">
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
                          color="bg-sky-400"
                        />
                      )
                    )}
                  </div>
                </div>
              </div>

              {/* Dataset notice */}
              <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-5">
                <div className="flex items-start gap-3">
                  <span className="text-amber-400">ⓘ</span>
                  <div>
                    <h4 className="text-sm font-medium text-amber-300">
                      Prototype Data Notice
                    </h4>
                    <p className="mt-1 text-xs leading-6 text-gray-400">
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

          <footer className="border-t border-white/10 pt-5 text-xs text-gray-600">
            MethaTrace · Prototype Dashboard · Chakan Industrial Zone
          </footer>
        </div>
      </section>
    </main>
  );
}
