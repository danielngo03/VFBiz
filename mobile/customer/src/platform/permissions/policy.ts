export type SensitivePermission =
  | "camera"
  | "location"
  | "notification"
  | "bluetooth"
  | "contacts";

export const phaseOnePermissionPolicy: Record<SensitivePermission, "blocked"> = {
  camera: "blocked",
  location: "blocked",
  notification: "blocked",
  bluetooth: "blocked",
  contacts: "blocked",
};
