import {Skeleton} from '@/components/ui/skeleton';

interface ResourceTableSkeletonProps {
  readonly columns: number;
  readonly rows?: number;
  readonly label: string;
}

export function ResourceTableSkeleton({
  columns,
  rows = 5,
  label,
}: ResourceTableSkeletonProps) {
  return (
    <div className="resource-table-skeleton" role="status" aria-live="polite">
      <span className="sr-only">{label}</span>
      <div className="resource-table-skeleton__header">
        {Array.from({length: columns}, (_, index) => (
          <Skeleton className="skeleton--heading" key={index} />
        ))}
      </div>
      {Array.from({length: rows}, (_, row) => (
        <div className="resource-table-skeleton__row" key={row}>
          {Array.from({length: columns}, (_, column) => (
            <Skeleton className="skeleton--cell" key={column} />
          ))}
        </div>
      ))}
    </div>
  );
}
