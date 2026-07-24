import { useId } from "react";
import { mergeClassNames } from "@/components/ui/class-names";

export interface StatusPanelProps {
  readonly description: string;
  readonly title: string;
  readonly tone: "information" | "success" | "warning";
}

export function StatusPanel({
  description,
  title,
  tone,
}: StatusPanelProps) {
  const headingId = `status-title-${useId()}`;

  return (
    <section
      className={mergeClassNames("status-panel", `status-panel-${tone}`)}
      aria-labelledby={headingId}
    >
      <h2 id={headingId}>{title}</h2>
      <p>{description}</p>
    </section>
  );
}
