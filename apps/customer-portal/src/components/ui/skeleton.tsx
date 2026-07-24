import type { CSSProperties } from "react";
import { mergeClassNames } from "./class-names";
import styles from "./skeleton.module.css";

interface SkeletonProps {
  readonly className?: string;
  readonly height?: CSSProperties["height"];
  readonly width?: CSSProperties["width"];
}

export function Skeleton({ className, height, width }: SkeletonProps) {
  return (
    <span
      aria-hidden="true"
      className={mergeClassNames(styles.skeleton, className)}
      style={{ height, width }}
    />
  );
}
