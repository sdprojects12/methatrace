export default function ModuleUnderDevelopment({ title }: { title: string }) {
  return (
    <div className="rounded-xl border border-border bg-surface p-8">
      <h3 className="text-2xl font-semibold tracking-tight">{title}</h3>
      <p className="mt-2 text-sm text-muted">Module under development</p>
    </div>
  );
}
