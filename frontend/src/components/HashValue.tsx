export function HashValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="hash-value">
      <span className="eyebrow">{label}</span>
      <code>{value}</code>
    </div>
  );
}
