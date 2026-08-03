export interface ApiProblem {
  type: string;
  title: string;
  status: number;
  detail?: string;
  instance?: string;
  correlationId?: string;
}

export class ApiProblemError extends Error {
  constructor(public readonly problem: ApiProblem) {
    super(problem.detail ?? problem.title);
    this.name = "ApiProblemError";
  }
}

export function problemFromResponse(
  status: number,
  body: unknown,
  correlationId?: string | null,
): ApiProblem {
  const value =
    typeof body === "object" && body !== null
      ? (body as Record<string, unknown>)
      : {};
  return {
    type: typeof value.type === "string" ? value.type : "about:blank",
    title:
      typeof value.title === "string" ? value.title : "Không thể hoàn tất yêu cầu",
    status,
    ...(typeof value.detail === "string" ? { detail: value.detail } : {}),
    ...(typeof value.instance === "string" ? { instance: value.instance } : {}),
    ...(correlationId ? { correlationId } : {}),
  };
}
