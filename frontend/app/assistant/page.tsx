"use client";

import { useEffect, useId, useRef, useState } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { fetchAPI, postAPI } from "../../src/lib/api";

type Role = "user" | "assistant";
type MessageStatus = "pending" | "success" | "failed";
interface ChatMessage { id: string; role: Role; content: string; status: MessageStatus; error?: string }
interface Pipeline { pipeline_id: string; type: string; status: string }
interface PipelineResponse { pipelines: Pipeline[] }
interface ChatResponse { reply: string; available: boolean }

const MAX_HISTORY = 8;
const suggestions = [
  "Explain the risk score of DIST-0068.",
  "Compare DIST-0068 and DIST-0129.",
  "Summarise the methane observations.",
  "Identify the highest-priority pipelines.",
  "Explain the sensor anomalies.",
];

const markdownComponents: Components = {
  h1: ({ children }) => <h1 className="mt-4 text-lg font-semibold text-foreground first:mt-0">{children}</h1>,
  h2: ({ children }) => <h2 className="mt-4 text-base font-semibold text-foreground first:mt-0">{children}</h2>,
  h3: ({ children }) => <h3 className="mt-3 text-sm font-semibold text-foreground first:mt-0">{children}</h3>,
  p: ({ children }) => <p className="my-2 whitespace-pre-wrap first:mt-0 last:mb-0">{children}</p>,
  ul: ({ children }) => <ul className="my-2 list-disc space-y-1 pl-5">{children}</ul>,
  ol: ({ children }) => <ol className="my-2 list-decimal space-y-1 pl-5">{children}</ol>,
  li: ({ children }) => <li className="ps-1">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
  em: ({ children }) => <em>{children}</em>,
  blockquote: ({ children }) => <blockquote className="my-3 border-l-2 border-accent/50 pl-3 text-muted">{children}</blockquote>,
  pre: ({ children }) => <pre className="my-3 overflow-x-auto rounded-lg bg-surface-sunken p-3 text-xs">{children}</pre>,
  code: ({ children, className }) => <code className={className ? "font-mono" : "rounded bg-surface-sunken px-1 py-0.5 font-mono text-[0.9em]"}>{children}</code>,
  table: ({ children }) => <div className="my-3 max-w-full overflow-x-auto rounded-lg border border-border"><table className="min-w-[520px] border-collapse text-left text-xs">{children}</table></div>,
  thead: ({ children }) => <thead className="bg-surface-sunken text-foreground">{children}</thead>,
  th: ({ children }) => <th className="border-b border-border px-3 py-2 font-semibold">{children}</th>,
  td: ({ children }) => <td className="border-b border-border px-3 py-2 align-top text-secondary">{children}</td>,
  a: ({ children, href }) => <a className="text-accent underline underline-offset-2" href={href}>{children}</a>,
};

function MessageText({ content }: { content: string }) {
  return <div className="text-sm leading-6">
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>{content}</ReactMarkdown>
  </div>;
}

function newId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export default function AssistantPage() {
  const pipelineSelectId = useId();
  const messageInputId = useId();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const messagesRef = useRef<ChatMessage[]>([]);
  const [selectedPipelineId, setSelectedPipelineId] = useState("");
  const [pipelines, setPipelines] = useState<Pipeline[]>([]);
  const [pipelineLoading, setPipelineLoading] = useState(true);
  const [pipelineError, setPipelineError] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const sendingRef = useRef(false);
  const requestController = useRef<AbortController | null>(null);
  const requestId = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    fetchAPI<PipelineResponse>("/api/pipelines", { signal: controller.signal })
      .then((result) => setPipelines(result.pipelines))
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) setPipelineError(cause instanceof Error ? cause.message : "Unable to load pipelines.");
      })
      .finally(() => { if (!controller.signal.aborted) setPipelineLoading(false); });
    return () => controller.abort();
  }, []);

  useEffect(() => () => {
    requestId.current += 1;
    const controller = requestController.current;
    requestController.current = null;
    controller?.abort();
    if (sendingRef.current) {
      sendingRef.current = false;
      setSending(false);
      const updated = messagesRef.current.map((message) =>
        message.status === "pending"
          ? { ...message, status: "failed" as const, error: "Request cancelled when you left the page. Retry to continue." }
          : message
      );
      messagesRef.current = updated;
      setMessages(updated);
    }
  }, []);

  async function submitMessage(messageId: string, content: string) {
    if (!content.trim() || sendingRef.current) return;
    const current = messagesRef.current;
    const historyMessages = current
      .filter((message) => message.status === "success")
      .slice(-MAX_HISTORY)
      .map(({ role, content: text }) => ({ role, content: text }));
    const pendingMessages = current.map((message) =>
      message.id === messageId ? { ...message, status: "pending" as const } : message
    );
    messagesRef.current = pendingMessages;
    setMessages(pendingMessages);
    setSending(true);
    sendingRef.current = true;
    const currentRequestId = ++requestId.current;
    const controller = new AbortController();
    requestController.current = controller;

    try {
      const result = await postAPI<ChatResponse>("/api/ai/chat", {
        message: content,
        selected_pipeline_id: selectedPipelineId || null,
        history: historyMessages.slice(-MAX_HISTORY).map(({ role, content: text }) => ({ role, content: text })),
      }, { signal: controller.signal, timeoutMs: 80_000 });
      if (controller.signal.aborted || currentRequestId !== requestId.current) return;
      const updated = [
        ...messagesRef.current.map((message) =>
          message.id === messageId ? { ...message, status: "success" as const } : message
        ),
        { id: newId(), role: "assistant" as const, content: result.reply, status: "success" as const },
      ];
      messagesRef.current = updated;
      setMessages(updated);
    } catch (cause) {
      if (!controller.signal.aborted && currentRequestId === requestId.current) {
        const failure = cause instanceof Error ? cause.message : "AI Analyst could not complete the request.";
        const updated = messagesRef.current.map((message) =>
          message.id === messageId
            ? { ...message, status: "failed" as const, error: failure }
            : message
        );
        messagesRef.current = updated;
        setMessages(updated);
      }
    } finally {
      if (currentRequestId === requestId.current) {
        requestController.current = null;
        sendingRef.current = false;
        setSending(false);
      }
    }
  }

  function sendMessage(raw: string) {
    const content = raw.trim();
    if (!content || sendingRef.current) return;
    const current = messagesRef.current;
    const pending = [
      ...current.filter((message) => message.status !== "failed"),
      { id: newId(), role: "user" as const, content, status: "pending" as const },
    ];
    messagesRef.current = pending;
    setMessages(pending);
    setInput("");
    void submitMessage(pending[pending.length - 1].id, content);
  }

  function retryMessage(message: ChatMessage) {
    if (message.role !== "user" || message.status !== "failed" || sendingRef.current) return;
    void submitMessage(message.id, message.content);
  }

  function dismissMessage(messageId: string) {
    const updated = messagesRef.current.filter((message) => message.id !== messageId);
    messagesRef.current = updated;
    setMessages(updated);
  }

  function resetConversation() {
    requestId.current += 1;
    requestController.current?.abort();
    requestController.current = null;
    sendingRef.current = false;
    setSending(false);
    setMessages([]);
    messagesRef.current = [];
    setInput("");
    setSelectedPipelineId("");
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h3 className="text-2xl font-semibold tracking-tight">AI Analyst</h3>
          <p className="mt-2 max-w-2xl text-sm text-muted">
            Ask questions about pipeline risk, methane observations, sensor telemetry, and inspection priorities.
          </p>
        </div>
        <button type="button" onClick={resetConversation} className="rounded-lg border border-border px-3 py-2 text-sm text-secondary transition hover:bg-surface-hover">
          Reset conversation
        </button>
      </div>

      <div className="rounded-xl border border-warning/25 bg-warning/5 px-4 py-3 text-xs leading-5 text-muted" role="note">
        Prototype data notice: methane observations are synthetic and sensor telemetry is simulated. AI explanations are informational and do not confirm field conditions or replace safety procedures.
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_18rem]">
        <section className="min-w-0 rounded-xl border border-border bg-surface" aria-label="Conversation">
          <div className="max-h-[min(62vh,720px)] min-h-[360px] space-y-5 overflow-y-auto p-4 sm:p-6" aria-live="polite" aria-relevant="additions text">
            {messages.length === 0 ? (
              <div className="flex min-h-[310px] flex-col justify-center">
                <h4 className="text-lg font-semibold">What would you like to investigate?</h4>
                <p className="mt-1 text-sm text-muted">Choose a prompt or ask your own question.</p>
                <div className="mt-5 grid gap-2 sm:grid-cols-2">
                  {suggestions.map((prompt) => <button key={prompt} type="button" onClick={() => void sendMessage(prompt)} disabled={sending} className="rounded-lg border border-border bg-surface-sunken px-3 py-3 text-left text-sm text-secondary transition hover:border-accent/40 hover:bg-surface-hover disabled:opacity-60">
                    {prompt}
                  </button>)}
                </div>
              </div>
            ) : messages.map((message) => (
              <article key={message.id} className={`max-w-[92%] rounded-xl px-4 py-3 sm:max-w-[85%] ${message.role === "user" ? "ml-auto border border-accent/25 bg-accent/10 text-foreground" : "mr-auto border border-border-subtle bg-surface-raised text-secondary"}`}>
                <div className="mb-1 flex items-center justify-between gap-3">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-muted">{message.role === "user" ? "You" : "AI Analyst"}</p>
                  {message.role === "user" && message.status === "pending" && <span className="text-[11px] text-muted" role="status">Sending…</span>}
                </div>
                <MessageText content={message.content} />
                {message.role === "user" && message.status === "failed" && <div className="mt-3 rounded-lg border border-danger/25 bg-danger/5 p-3" role="alert">
                  <p className="text-xs text-danger">{message.error}</p>
                  <div className="mt-2 flex gap-2">
                    <button type="button" onClick={() => retryMessage(message)} disabled={sending} className="rounded-md border border-danger/30 px-3 py-1.5 text-xs text-danger hover:bg-danger/10 disabled:opacity-60">Retry</button>
                    <button type="button" onClick={() => dismissMessage(message.id)} disabled={sending} className="rounded-md border border-border px-3 py-1.5 text-xs text-secondary hover:bg-surface-hover disabled:opacity-60">Dismiss</button>
                  </div>
                </div>}
              </article>
            ))}
            {sending && <div className="mr-auto flex items-center gap-3 rounded-xl border border-border-subtle bg-surface-raised px-4 py-3 text-sm text-muted" role="status" aria-live="polite">
              <span className="h-2 w-2 animate-pulse rounded-full bg-accent" />Analyzing available MethaTrace data…
            </div>}
          </div>

          <form className="border-t border-border p-4 sm:p-5" onSubmit={(event) => { event.preventDefault(); void sendMessage(input); }}>
            <label htmlFor={messageInputId} className="sr-only">Ask the AI Analyst</label>
            <textarea id={messageInputId} value={input} maxLength={1500} rows={3} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void sendMessage(input); }
            }} placeholder="Ask about risk, methane, sensors, or priorities…" className="w-full resize-y rounded-lg border border-border bg-surface-sunken px-3 py-3 text-sm text-foreground outline-none placeholder:text-subtle focus:border-accent/60" />
            <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
              <span className="text-xs text-muted">Enter to send · Shift+Enter for a new line · {input.length}/1500</span>
              <button type="submit" disabled={sending || !input.trim()} className="rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-accent-contrast transition hover:bg-accent-strong disabled:cursor-not-allowed disabled:opacity-50">
                {sending ? "Thinking…" : "Send message"}
              </button>
            </div>
          </form>
        </section>

        <aside className="space-y-4">
          <section className="rounded-xl border border-border bg-surface p-4">
            <label htmlFor={pipelineSelectId} className="text-sm font-semibold">Pipeline context</label>
            <p className="mt-1 text-xs leading-5 text-muted">Select an asset to include its current backend risk assessment and relevant readings.</p>
            {pipelineLoading ? <p className="mt-3 text-sm text-muted">Loading pipelines…</p> : pipelineError ? <div className="mt-3 space-y-2" role="alert"><p className="text-xs text-danger">{pipelineError}</p><button type="button" onClick={() => { setPipelineError(null); setPipelineLoading(true); fetchAPI<PipelineResponse>("/api/pipelines").then((result) => setPipelines(result.pipelines)).catch((cause: unknown) => setPipelineError(cause instanceof Error ? cause.message : "Unable to load pipelines.")).finally(() => setPipelineLoading(false)); }} className="text-xs text-accent underline">Retry</button></div> : <select id={pipelineSelectId} value={selectedPipelineId} onChange={(event) => setSelectedPipelineId(event.target.value)} className="mt-3 w-full rounded-lg border border-border bg-surface-sunken px-3 py-2.5 text-sm text-secondary outline-none focus:border-accent/60">
              <option value="">No selected pipeline</option>
              {pipelines.map((pipeline) => <option key={pipeline.pipeline_id} value={pipeline.pipeline_id}>{pipeline.pipeline_id} · {pipeline.type} · {pipeline.status}</option>)}
            </select>}
          </section>
          {messages.length > 0 && <div className="flex flex-wrap gap-2">
            {suggestions.slice(2).map((prompt) => <button key={prompt} type="button" onClick={() => void sendMessage(prompt)} disabled={sending} className="rounded-full border border-border px-3 py-2 text-xs text-muted hover:bg-surface-hover disabled:opacity-50">{prompt}</button>)}
          </div>}
          <p className="px-1 text-xs leading-5 text-subtle">Answers use only available MethaTrace data and backend risk assessments. Missing readings remain unavailable; the assistant does not calculate scores.</p>
        </aside>
      </div>
    </div>
  );
}
