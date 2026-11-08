const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

const DEFAULT_TIMEOUT_MS = 15_000;

export class ApiError extends Error {
  status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function friendlyStatus(status: number) {
  if (status === 404) return "The requested data is not available.";
  if (status >= 500) return "The data service is temporarily unavailable.";
  return "The request could not be completed.";
}

async function request(
  endpoint: string,
  signal?: AbortSignal,
  init: RequestInit = {},
  timeoutMs = DEFAULT_TIMEOUT_MS
): Promise<Response> {
  const controller = new AbortController();
  const abortFromCaller = () => controller.abort(signal?.reason);
  signal?.addEventListener("abort", abortFromCaller, { once: true });
  const timeout = setTimeout(
    () => controller.abort(new DOMException("Request timed out", "TimeoutError")),
    timeoutMs
  );

  try {
    const response = await fetch(`${API_URL}${endpoint}`, {
      ...init,
      cache: "no-store",
      signal: controller.signal,
    });
    if (!response.ok) {
      let detail: string | undefined;
      try {
        const body = (await response.clone().json()) as { detail?: unknown };
        if (typeof body.detail === "string") detail = body.detail;
      } catch {
        // Retain the friendly status message if the response isn't JSON.
      }
      throw new ApiError(detail ?? friendlyStatus(response.status), response.status);
    }
    return response;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (signal?.aborted) throw new DOMException("Request cancelled", "AbortError");
    if (controller.signal.aborted) {
      throw new ApiError("The request timed out. Please try again.");
    }
    throw new ApiError("Unable to reach the data service. Check your connection and try again.");
  } finally {
    clearTimeout(timeout);
    signal?.removeEventListener("abort", abortFromCaller);
  }
}

export async function fetchAPI<T>(
  endpoint: string,
  options: { signal?: AbortSignal } = {}
): Promise<T> {
  const response = await request(endpoint, options.signal);
  return response.json() as Promise<T>;
}

export async function fetchAPIBlob(
  endpoint: string,
  options: { signal?: AbortSignal } = {}
): Promise<Blob> {
  const response = await request(endpoint, options.signal);
  return response.blob();
}

export async function postAPI<T>(
  endpoint: string,
  body: unknown,
  options: { signal?: AbortSignal; timeoutMs?: number } = {}
): Promise<T> {
  const response = await request(endpoint, options.signal, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }, options.timeoutMs);
  return response.json() as Promise<T>;
}
