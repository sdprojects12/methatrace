import { fetchAPIBlob } from "./api";

/**
 * Request a pipeline PDF report and trigger a browser download.
 * Shared by every report entry point so generation behaves consistently.
 */
export async function downloadPipelineReport(
  pipelineId: string
): Promise<void> {
  const blob = await fetchAPIBlob(
    `/api/reports/${encodeURIComponent(pipelineId)}.pdf`
  );
  const url = URL.createObjectURL(blob);

  try {
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `MethaTrace-${pipelineId}.pdf`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}
