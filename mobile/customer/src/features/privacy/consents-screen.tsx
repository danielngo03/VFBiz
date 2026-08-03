import { StyleSheet, View } from "react-native";
import { AppIcon, EmptyState, LoadingState, Screen, StatusPill, Surface, Text } from "../../design/components";
import { useCustomerTheme } from "../../design/theme/theme";
import { formatCustomerDateTime } from "../../platform/i18n/format";
import { useCustomerConsents } from "../../state/queries/customer-queries";

const purposeLabels: Record<string, string> = {
  analytics: "Phân tích trải nghiệm",
  marketing_email: "Tiếp thị qua email",
  marketing_sms: "Tiếp thị qua SMS",
  marketing_push: "Thông báo tiếp thị",
  personalization: "Cá nhân hóa",
};

export function ConsentsScreen() {
  const theme = useCustomerTheme();
  const consents = useCustomerConsents();
  if (consents.isLoading) return <Screen><LoadingState label="Đang tải đồng thuận" /></Screen>;
  const records = consents.data?.data ?? [];
  return (
    <Screen>
      <Text variant="display">Đồng thuận</Text>
      <Text muted>Mỗi lựa chọn gắn với mục đích, nguồn và phiên bản chính sách cụ thể.</Text>
      {records.length === 0 ? (
        <EmptyState title="Chưa có lựa chọn" detail="Các mục đích hợp lệ sẽ xuất hiện cùng phiên bản chính sách." />
      ) : records.map((record) => (
        <Surface key={record.purpose} style={styles.card}>
          <View style={[styles.icon, { backgroundColor: theme.surfaceSubtle }]}><AppIcon name="fact_check" color={theme.accent} /></View>
          <View style={styles.grow}>
            <Text variant="title">{purposeLabels[record.purpose] ?? record.purpose}</Text>
            <Text variant="caption" muted>Chính sách {record.policyVersion} · {formatCustomerDateTime(record.occurredAt)}</Text>
          </View>
          <StatusPill state={record.state === "granted" ? "verified" : "restricted"} />
        </Surface>
      ))}
      <Text variant="caption" muted style={styles.center}>Thay đổi đồng thuận chỉ mở khi mutation và policy-version conflict đã được kiểm thử end-to-end.</Text>
    </Screen>
  );
}

const styles = StyleSheet.create({
  card: { flexDirection: "row", alignItems: "center", gap: 14 },
  icon: { width: 48, height: 48, borderRadius: 16, alignItems: "center", justifyContent: "center" },
  grow: { flex: 1, gap: 4 },
  center: { textAlign: "center" },
});
