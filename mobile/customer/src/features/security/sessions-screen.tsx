import { StyleSheet, View } from "react-native";
import { AppIcon, EmptyState, LoadingState, ProblemState, Screen, StatusPill, Surface, Text } from "../../design/components";
import { useCustomerTheme } from "../../design/theme/theme";
import { formatCustomerDateTime } from "../../platform/i18n/format";
import { useCustomerSessions } from "../../state/queries/customer-queries";

export function SessionsScreen() {
  const theme = useCustomerTheme();
  const sessions = useCustomerSessions();
  if (sessions.isLoading) return <Screen><LoadingState label="Đang tải phiên" /></Screen>;
  if (!sessions.data) return <Screen><ProblemState title="Không tải được phiên" detail="Thử lại khi có kết nối." /></Screen>;
  const items = sessions.data.data;
  return (
    <Screen>
      <Text variant="display">Phiên đăng nhập</Text>
      <Text muted>Theo dõi thiết bị đã dùng tài khoản và bằng chứng MFA của từng phiên.</Text>
      {items.length === 0 ? <EmptyState title="Không có phiên" detail="Identity authority chưa trả phiên hoạt động." /> : items.map((session) => (
        <Surface key={session.id} style={styles.card}>
          <View style={[styles.deviceIcon, { backgroundColor: theme.surfaceSubtle }]}>
            <AppIcon name={session.isCurrent ? "smartphone" : "devices"} color={theme.accent} />
          </View>
          <View style={styles.grow}>
            <View style={styles.titleRow}>
              <Text variant="title" style={styles.grow}>{session.deviceLabel ?? "Thiết bị chưa đặt tên"}</Text>
              <StatusPill state={session.status === "active" ? "verified" : "stale"} />
            </View>
            <Text variant="caption" muted>{session.isCurrent ? "Thiết bị hiện tại" : `Hoạt động ${formatCustomerDateTime(session.lastSeenAt)}`}</Text>
            <Text variant="caption" muted>{session.mfaSatisfied ? "Có bằng chứng MFA" : "Không có bằng chứng MFA"}</Text>
          </View>
        </Surface>
      ))}
      <Text variant="caption" muted style={styles.center}>
        Thu hồi phiên từ mobile chỉ mở sau khi reconciliation contract được kiểm thử; app không tuyên bố thu hồi thành công chỉ dựa trên thao tác cục bộ.
      </Text>
    </Screen>
  );
}

const styles = StyleSheet.create({
  card: { flexDirection: "row", alignItems: "flex-start", gap: 14 },
  deviceIcon: { width: 50, height: 50, borderRadius: 17, alignItems: "center", justifyContent: "center" },
  grow: { flex: 1, gap: 5 },
  titleRow: { flexDirection: "row", alignItems: "center", gap: 10 },
  center: { textAlign: "center" },
});
