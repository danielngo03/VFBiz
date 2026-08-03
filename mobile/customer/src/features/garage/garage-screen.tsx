import { router } from "expo-router";
import { Pressable, StyleSheet, View } from "react-native";
import {
  AppIcon,
  Button,
  EmptyState,
  LoadingState,
  ProblemState,
  Screen,
  StatusPill,
  Text,
  VehicleSilhouette,
} from "../../design/components";
import { useCustomerTheme } from "../../design/theme/theme";
import {
  resourceFreshness,
  useConnectivity,
} from "../../platform/network/connectivity";
import { useCustomerGarage } from "../../state/queries/customer-queries";

export function GarageScreen() {
  const theme = useCustomerTheme();
  const garage = useCustomerGarage();
  const connectivity = useConnectivity();
  if (garage.isLoading)
    return <Screen><LoadingState label="Đang chuẩn bị garage" /></Screen>;
  if (garage.isError)
    return <Screen><ProblemState title="Chưa tải được garage" detail="Kiểm tra kết nối rồi thử lại." /></Screen>;
  const entries = garage.data?.data ?? [];
  return (
    <Screen>
      <View style={styles.header}>
        <View style={styles.grow}>
          <Text variant="caption" muted>KHÔNG GIAN CỦA BẠN</Text>
          <Text variant="display">Garage</Text>
        </View>
        <View style={[styles.count, { backgroundColor: theme.surfaceSubtle }]}>
          <Text variant="title">{entries.length}</Text>
        </View>
      </View>
      <View style={styles.statusRow}>
        <StatusPill state={resourceFreshness({ connectivity, hasData: Boolean(garage.data), stale: garage.isStale, error: garage.isError })} />
        <Text variant="caption" muted>Xe tự khai báo ≠ quyền sở hữu</Text>
      </View>

      {entries.length === 0 ? (
        <View style={[styles.emptyCard, { backgroundColor: theme.surface, borderColor: theme.border }]}>
          <View style={[styles.emptyIcon, { backgroundColor: theme.surfaceSubtle }]}>
            <AppIcon name="add_road" size={32} color={theme.accent} />
          </View>
          <EmptyState title="Garage đang chờ chiếc xe đầu tiên" detail="Chọn model và phiên bản từ catalog chính thức để bắt đầu cá nhân hóa trải nghiệm." />
        </View>
      ) : (
        entries.map((entry, index) => (
          <Pressable
            key={entry.id}
            accessibilityRole="button"
            accessibilityLabel={`Mở ${entry.nickname ?? `xe ${index + 1}`}`}
            onPress={() => router.push({ pathname: "/(owner)/garage/[garageEntryId]", params: { garageEntryId: entry.id } })}
            style={({ pressed }) => [
              styles.vehicleCard,
              {
                backgroundColor: index === 0 ? theme.accentStrong : theme.surface,
                borderColor: index === 0 ? theme.accentStrong : theme.border,
                opacity: pressed ? 0.86 : 1,
              },
            ]}
          >
            <View style={styles.vehicleHeader}>
              <View style={styles.grow}>
                <Text variant="caption" style={{ color: index === 0 ? `${theme.onAccent}AD` : theme.textMuted }}>
                  {entry.isPrimary ? "XE CHÍNH" : `XE ${index + 1}`}
                </Text>
                <Text variant="title" style={index === 0 ? { color: theme.onAccent } : undefined}>
                  {entry.nickname ?? "Xe của tôi"}
                </Text>
              </View>
              <AppIcon name="arrow_outward" color={index === 0 ? theme.onAccent : theme.text} />
            </View>
            {index === 0 ? <VehicleSilhouette compact /> : null}
            <View style={styles.vehicleMeta}>
              <StatusPill state="unverified" />
              <Text variant="caption" style={{ color: index === 0 ? `${theme.onAccent}AD` : theme.textMuted }}>
                {entry.source === "self-reported" ? "Tự khai báo" : "Đã nhập"}
              </Text>
            </View>
          </Pressable>
        ))
      )}
      <Button label="Thêm xe vào garage" onPress={() => router.push("/(owner)/garage/add")} />
      <Text variant="caption" muted style={styles.footnote}>
        Garage không hiển thị pin, vị trí, khóa cửa hay sạc khi chưa có nguồn authority xác thực.
      </Text>
    </Screen>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", gap: 16, paddingTop: 8 },
  grow: { flex: 1, gap: 3 },
  count: { width: 52, height: 52, borderRadius: 18, alignItems: "center", justifyContent: "center" },
  statusRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 12 },
  emptyCard: { borderRadius: 28, borderWidth: StyleSheet.hairlineWidth, padding: 20, alignItems: "center" },
  emptyIcon: { width: 60, height: 60, borderRadius: 20, alignItems: "center", justifyContent: "center", marginTop: 8 },
  vehicleCard: { minHeight: 154, borderRadius: 28, borderWidth: StyleSheet.hairlineWidth, padding: 20, gap: 14, overflow: "hidden" },
  vehicleHeader: { flexDirection: "row", alignItems: "flex-start", gap: 12 },
  vehicleMeta: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 12 },
  footnote: { textAlign: "center", paddingHorizontal: 18 },
});
