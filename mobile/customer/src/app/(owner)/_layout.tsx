import { Redirect, Stack } from "expo-router";
import { LoadingState, Screen } from "../../design/components";
import { useAuth } from "../../platform/auth/auth-context";
import { ownerRouteDecision } from "../../platform/auth/owner-route";
import { useCustomerTheme } from "../../design/theme/theme";

export default function OwnerLayout() {
  const auth = useAuth();
  const theme = useCustomerTheme();
  const decision = ownerRouteDecision(auth.status, Boolean(auth.credential));
  if (decision === "loading")
    return <Screen><LoadingState label="Đang xác minh quyền truy cập" /></Screen>;
  if (decision === "sign-in") return <Redirect href="/sign-in" />;
  return (
    <Stack
      screenOptions={{
        headerBackTitle: "Quay lại",
        headerShadowVisible: false,
        headerStyle: { backgroundColor: theme.canvas },
        headerTintColor: theme.text,
        contentStyle: { backgroundColor: theme.canvas },
      }}
    >
      <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
      <Stack.Screen name="garage/add" options={{ title: "Thêm xe" }} />
      <Stack.Screen name="garage/[garageEntryId]" options={{ title: "Chi tiết xe" }} />
      <Stack.Screen name="account/profile" options={{ title: "Hồ sơ" }} />
      <Stack.Screen name="account/security" options={{ title: "Bảo mật" }} />
      <Stack.Screen name="account/sessions" options={{ title: "Phiên đăng nhập" }} />
      <Stack.Screen name="account/privacy" options={{ title: "Quyền riêng tư" }} />
      <Stack.Screen name="account/consents" options={{ title: "Đồng thuận" }} />
      <Stack.Screen name="support/index" options={{ title: "Hỗ trợ" }} />
      <Stack.Screen name="assistant/index" options={{ title: "ViVi" }} />
    </Stack>
  );
}
