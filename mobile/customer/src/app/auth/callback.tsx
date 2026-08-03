import { Redirect } from "expo-router";
import { LoadingState, Screen } from "../../design/components";
import { useAuth } from "../../platform/auth/auth-context";

export default function AuthCallbackRoute() {
  const auth = useAuth();
  if (auth.credential) return <Redirect href="/(owner)/(tabs)" />;
  if (["anonymous", "error"].includes(auth.status))
    return <Redirect href="/sign-in" />;
  return <Screen><LoadingState label="Đang xác nhận phiên đăng nhập" /></Screen>;
}
