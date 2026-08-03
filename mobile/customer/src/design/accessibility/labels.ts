export function statusAccessibilityLabel(label: string, detail?: string): string {
  return detail ? `Trạng thái: ${label}. ${detail}` : `Trạng thái: ${label}`;
}
