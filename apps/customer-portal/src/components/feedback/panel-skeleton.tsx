import { Skeleton } from "@/components/ui/skeleton";

interface PanelSkeletonProps {
  readonly fields?: number;
  readonly label: string;
}

export function PanelSkeleton({ fields = 3, label }: PanelSkeletonProps) {
  return (
    <section
      className="surface-card panel-skeleton"
      aria-busy="true"
      aria-label={label}
      role="status"
    >
      <span className="sr-only">{label}</span>
      <Skeleton height="1.75rem" width="38%" />
      {Array.from({ length: fields }, (_, index) => (
        <div className="panel-skeleton-field" key={index}>
          <Skeleton height="0.75rem" width="24%" />
          <Skeleton height="2.75rem" width="100%" />
        </div>
      ))}
    </section>
  );
}
