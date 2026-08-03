import path from "node:path";
import { BoundaryViolationError } from "../domain/errors.js";

export const allowedRuntimeTools = new Set([
  "repository-read",
  "repository-search",
  "codex-fixture-read",
  "codex-fixture-write",
  "request-approval",
]);

export const forbiddenProductPrefixes = [
  "backend/",
  "apps/",
  "mobile/",
  "drupal/",
  "infra/",
  "packages/",
] as const;

export function assertToolAllowed(toolName: string): void {
  if (!allowedRuntimeTools.has(toolName)) {
    throw new BoundaryViolationError(`tool is unavailable in runtime v1: ${toolName}`);
  }
}

export function assertProgramPathAllowed(candidate: string): void {
  const normalized = candidate.replaceAll(path.sep, "/").replace(/^\.\//, "");
  if (path.isAbsolute(candidate) || normalized.includes("../")) {
    throw new BoundaryViolationError(`path escapes declared runtime scope: ${candidate}`);
  }
  if (forbiddenProductPrefixes.some((prefix) => normalized.startsWith(prefix))) {
    throw new BoundaryViolationError(`product workspace path is forbidden: ${candidate}`);
  }
}
