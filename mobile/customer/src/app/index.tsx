import { Redirect } from "expo-router";
import { LoadingState, Screen } from "../design/components";
import { useAuth } from "../platform/auth/auth-context";

export default function IndexRoute() {
  const auth = useAuth();
  if (auth.status === "restoring")
    return <Screen><LoadingState label="Đang khôi phục phiên bảo mật" /></Screen>;
  return (
    <Redirect
      href={auth.credential ? "/(owner)/(tabs)" : "/sign-in"}
    />
  );
}
