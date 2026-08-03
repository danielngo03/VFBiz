import { StyleSheet, View } from "react-native";
import { AppIcon, InfoRow, LoadingState, ProblemState, Screen, StatusPill, Surface, Text } from "../../../design/components";
import { useCustomerTheme } from "../../../design/theme/theme";
import { useCustomerSecurity } from "../../../state/queries/customer-queries";

export default function SecurityRoute() {
  const theme = useCustomerTheme();
  const security = useCustomerSecurity();
  if (security.isLoading) return <Screen><LoadingState label="Đang tải trạng thái bảo mật" /></Screen>;
  if (!security.data) return <Screen><ProblemState title="Chưa có trạng thái bảo mật" detail="Identity provider hiện không khả dụng hoặc chưa trả authority." /></Screen>;
  const value = security.data.data;
  const label = (state: boolean | null, yes: string, no: string) => state === null ? "Chưa xác định" : state ? yes : no;
  return (
    <Screen>
      <View style={[styles.hero, { backgroundColor: theme.accentStrong }]}>
        <View style={styles.heroIcon}><AppIcon name="shield_lock" size={34} color={theme.onAccent} /></View>
        <Text variant="display" style={{ color: theme.onAccent }}>Bảo vệ tài khoản</Text>
        <Text style={{ color: `${theme.onAccent}C2` }}>
          Trạng thái dưới đây đến trực tiếp từ Identity authority, không được suy đoán trên thiết bị.
        </Text>
      </View>
      <StatusPill state={value.providerStatus === "available" ? "fresh" : "unknown"} />
      <Surface style={styles.details}>
        <InfoRow icon="mark_email_read" label="Email" value={label(value.emailVerified, "Đã xác minh", "Chưa xác minh")} />
        <InfoRow icon="key" label="MFA" value={label(value.mfaConfigured, "Đã cấu hình", "Chưa cấu hình")} />
        <InfoRow icon="verified_user" label="Phiên hiện tại" value={value.currentSessionMfaSatisfied ? "Có bằng chứng MFA" : "Chưa có MFA"} last />
      </Surface>
    </Screen>
  );
}

const styles = StyleSheet.create({
  hero: { borderRadius: 30, padding: 24, gap: 12, overflow: "hidden" },
  heroIcon: { width: 58, height: 58, borderRadius: 20, backgroundColor: "rgba(255,255,255,0.13)", alignItems: "center", justifyContent: "center" },
  details: { paddingVertical: 4 },
});
