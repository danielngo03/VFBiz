interface FoundationPanelProps {
  readonly eyebrow: string;
  readonly title: string;
  readonly description: string;
  readonly requiredCapability: string;
}

export function FoundationPanel({
  eyebrow,
  title,
  description,
  requiredCapability,
}: FoundationPanelProps) {
  return (
    <section className="panel" aria-labelledby="foundation-panel-title">
      <p className="eyebrow">{eyebrow}</p>
      <h1 id="foundation-panel-title">{title}</h1>
      <p>{description}</p>
      <dl className="contract-summary">
        <div>
          <dt>Capability yêu cầu</dt>
          <dd><code>{requiredCapability}</code></dd>
        </div>
        <div>
          <dt>Authority</dt>
          <dd>NestJS Authorization Platform</dd>
        </div>
        <div>
          <dt>Trạng thái</dt>
          <dd>Foundation · chưa kết nối dữ liệu thật</dd>
        </div>
      </dl>
    </section>
  );
}
