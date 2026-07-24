import { normalizeCustomerReturnTo } from "./safe-return-to";

export interface JsonFetchResponse {
  readonly ok: boolean;
  readonly status: number;
  json(): Promise<unknown>;
}

export type JsonFetch = (
  input: string,
  init: {
    readonly method: string;
    readonly credentials: "include";
    readonly headers: Readonly<Record<string, string>>;
    readonly body?: string;
  },
) => Promise<JsonFetchResponse>;

export class BffRequestError extends Error {
  readonly status: number;

  constructor(status: number) {
    super("The account request could not be completed.");
    this.name = "BffRequestError";
    this.status = status;
  }
}

export class MemoryOnlyCsrfToken {
  #token: string | null = null;

  set(token: string): void {
    if (!token) throw new Error("A CSRF token is required.");
    this.#token = token;
  }

  read(): string | null {
    return this.#token;
  }

  clear(): void {
    this.#token = null;
  }
}

export type CustomerAuthAction =
  "configure-mfa" | "login" | "register" | "reset-password";

export function customerAuthHref(
  action: CustomerAuthAction,
  returnTo?: string,
): string {
  const path = `/api/auth/${action}`;
  if (
    action === "reset-password" ||
    returnTo === undefined ||
    returnTo.trim().length === 0
  ) {
    return path;
  }
  const safeReturnTo = normalizeCustomerReturnTo(returnTo);
  if (safeReturnTo === null) {
    return path;
  }
  const query = new URLSearchParams({ returnTo: safeReturnTo });
  return `${path}?${query.toString()}`;
}

export class CustomerBffClient {
  readonly #fetch: JsonFetch;
  readonly #csrf: MemoryOnlyCsrfToken;

  constructor(fetchImplementation: JsonFetch, csrf: MemoryOnlyCsrfToken) {
    this.#fetch = fetchImplementation;
    this.#csrf = csrf;
  }

  async get(path: string): Promise<unknown> {
    return this.#request("GET", path);
  }

  async mutate(path: string, body: unknown): Promise<unknown> {
    return this.post(path, body);
  }

  async post(path: string, body?: unknown): Promise<unknown> {
    return this.#mutation("POST", path, body);
  }

  async put(path: string, body: unknown): Promise<unknown> {
    return this.#mutation("PUT", path, body);
  }

  async patch(path: string, body: unknown): Promise<unknown> {
    return this.#mutation("PATCH", path, body);
  }

  async delete(path: string, body?: unknown): Promise<unknown> {
    return this.#mutation("DELETE", path, body);
  }

  async #mutation(
    method: "DELETE" | "PATCH" | "POST" | "PUT",
    path: string,
    body?: unknown,
  ): Promise<unknown> {
    const csrfToken = this.#csrf.read();
    if (!csrfToken) throw new BffRequestError(403);
    return this.#request(method, path, body, csrfToken);
  }

  async #request(
    method: "DELETE" | "GET" | "PATCH" | "POST" | "PUT",
    path: string,
    body?: unknown,
    csrfToken?: string,
  ): Promise<unknown> {
    if (!path.startsWith("/bff/"))
      throw new Error(
        "Customer requests must use the same-origin BFF boundary.",
      );
    const headers: Record<string, string> = { accept: "application/json" };
    if (body !== undefined) headers["content-type"] = "application/json";
    if (csrfToken) headers["x-csrf-token"] = csrfToken;
    const response = await this.#fetch(path, {
      method,
      credentials: "include",
      headers,
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    if (!response.ok) throw new BffRequestError(response.status);
    return response.json();
  }
}
