import { StyleSheet, View } from "react-native";
import { AppIcon, EmptyState, LoadingState, Screen, StatusPill, Surface, Text } from "../../../design/components";
import { useCustomerTheme } from "../../../design/theme/theme";
import { formatCustomerDateTime } from "../../../platform/i18n/format";
import { useCustomerDataRequests } from "../../../state/queries/customer-queries";

export default function PrivacyRoute() {
  const theme = useCustomerTheme();
  const requests = useCustomerDataRequests();
  if (requests.isLoading) return <Screen><LoadingState label="Đang tải yêu cầu dữ liệu" /></Screen>;
  const items = requests.data?.data ?? [];
  return (
    <Screen>
      <View style={styles.header}>
        <View style={[styles.icon, { backgroundColor: theme.surfaceSubtle }]}><AppIcon name="privacy_tip" color={theme.accent} size={30} /></View>
        <View style={styles.grow}><Text variant="display">Quyền riêng tư</Text><Text muted>Dữ liệu của bạn, trạng thái rõ ràng.</Text></View>
      </View>
      <Surface style={[styles.notice, { backgroundColor: theme.surfaceSubtle }]}>
        <AppIcon name="info" color={theme.accent} />
        <Text variant="caption" muted style={styles.grow}>Xuất hoặc xóa dữ liệu là server workflow. App chỉ hiển thị trạng thái do API authority xác nhận.</Text>
      </Surface>
      {items.length === 0 ? (
        <EmptyState title="Chưa có yêu cầu dữ liệu" detail="Khi capability tạo yêu cầu được phê duyệt, tiến trình sẽ xuất hiện tại đây." />
      ) : items.map((item) => (
        <Surface key={item.id} style={styles.requestCard}>
          <View style={[styles.requestIcon, { backgroundColor: theme.surfaceSubtle }]}>
            <AppIcon name={item.type === "export" ? "download" : "delete_forever"} color={item.type === "delete" ? theme.danger : theme.accent} />
          </View>
          <View style={styles.grow}>
            <Text variant="title">{item.type === "export" ? "Xuất dữ liệu" : "Xóa dữ liệu"}</Text>
            <Text variant="caption" muted>{formatCustomerDateTime(item.requestedAt)}</Text>
          </View>
          <StatusPill state={item.status === "completed" ? "verified" : item.status === "rejected" ? "restricted" : "pending"} />
        </Surface>
      ))}
    </Screen>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", gap: 14, paddingTop: 8 },
  icon: { width: 58, height: 58, borderRadius: 20, alignItems: "center", justifyContent: "center" },
  grow: { flex: 1, gap: 3 },
  notice: { flexDirection: "row", alignItems: "flex-start", gap: 12 },
  requestCard: { flexDirection: "row", alignItems: "center", gap: 14 },
  requestIcon: { width: 48, height: 48, borderRadius: 16, alignItems: "center", justifyContent: "center" },
});
