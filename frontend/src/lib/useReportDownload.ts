"use client";

import { useCallback, useRef, useState } from "react";
import { downloadPipelineReport } from "./report";

export interface ReportDownloadState {
  /** True while a report request is in flight. */
  generating: boolean;
  /** Error message from the most recent attempt, if any. */
  error: string | null;
  /** Pipeline ID of the most recently downloaded report, if any. */
  downloaded: string | null;
  /** Request and download a report; returns true on success. */
  download: (pipelineId: string) => Promise<boolean>;
  /** Clear success and error feedback. */
  reset: () => void;
}

/**
 * Shared report-generation state, including an in-flight guard so repeated
 * clicks cannot start overlapping PDF requests.
 */
export function useReportDownload(): ReportDownloadState {
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [downloaded, setDownloaded] = useState<string | null>(null);
  const inFlight = useRef(false);

  const download = useCallback(async (pipelineId: string) => {
    if (!pipelineId || inFlight.current) return false;

    inFlight.current = true;
    setGenerating(true);
    setError(null);
    setDownloaded(null);

    try {
      await downloadPipelineReport(pipelineId);
      setDownloaded(pipelineId);
      return true;
    } catch (cause: unknown) {
      setError(
        cause instanceof Error ? cause.message : "Unable to generate report."
      );
      return false;
    } finally {
      inFlight.current = false;
      setGenerating(false);
    }
  }, []);

  const reset = useCallback(() => {
    setError(null);
    setDownloaded(null);
  }, []);

  return { generating, error, downloaded, download, reset };
}
