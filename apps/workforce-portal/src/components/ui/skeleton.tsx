interface SkeletonProps {
  readonly className?: string;
}

export function Skeleton({className = ''}: SkeletonProps) {
  return <span aria-hidden="true" className={`skeleton ${className}`.trim()} />;
}
