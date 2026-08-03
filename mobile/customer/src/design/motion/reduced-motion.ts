import { AccessibilityInfo } from "react-native";

export async function motionDuration(preferred: number): Promise<number> {
  return (await AccessibilityInfo.isReduceMotionEnabled()) ? 0 : preferred;
}
