export interface ProfileActionState {
  readonly correlationId?: string;
  readonly fieldErrors?: Readonly<Record<string, readonly string[]>>;
  readonly message?: string;
  readonly status: "idle" | "success" | "invalid" | "conflict" | "error";
}

export const initialProfileActionState: ProfileActionState = {
  status: "idle",
};
