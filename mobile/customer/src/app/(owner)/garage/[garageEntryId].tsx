import { useLocalSearchParams } from "expo-router";
import { StyleSheet, View } from "react-native";
import {
  AppIcon,
  LoadingState,
  ProblemState,
  Screen,
  StatusPill,
  Surface,
  Text,
  VehicleSilhouette,
} from "../../../design/components";
import { useCustomerTheme } from "../../../design/theme/theme";
import { useCustomerGarage } from "../../../state/queries/customer-queries";

export default function GarageEntryRoute() {
  const theme = useCustomerTheme();
  const { garageEntryId } = useLocalSearchParams<{ garageEntryId: string }>();
  const garage = useCustomerGarage();
  if (garage.isLoading)
    return <Screen><LoadingState label="Đang tải chi tiết xe" /></Screen>;
  const entry = garage.data?.data.find((item) => item.id === garageEntryId);
  if (!entry)
    return <Screen><ProblemState title="Không tìm thấy xe" detail="Xe không tồn tại trong garage hiện tại hoặc đã được lưu trữ." /></Screen>;
  return (
    <Screen>
      <View style={[styles.hero, { backgroundColor: theme.accentStrong }]}>
        <View style={styles.heroHeader}>
          <View style={styles.grow}>
            <Text variant="caption" style={{ color: `${theme.onAccent}AD` }}>
              {entry.isPrimary ? "XE CHÍNH" : "GARAGE CỦA BẠN"}
            </Text>
            <Text variant="display" style={{ color: theme.onAccent }}>{entry.nickname ?? "Xe của tôi"}</Text>
          </View>
          <View style={styles.heroIcon}>
            <AppIcon name="directions_car" color={theme.onAccent} />
          </View>
        </View>
        <VehicleSilhouette />
      </View>

      <View style={styles.statusRow}>
        <StatusPill state="unverified" />
        <Text variant="caption" muted>{entry.status === "active" ? "Đang hoạt động" : "Đã lưu trữ"}</Text>
      </View>

      <Surface style={styles.details}>
        <DetailRow icon="garage_home" label="Nguồn" value={entry.source === "self-reported" ? "Tự khai báo" : "Đã nhập"} />
        <DetailRow icon="verified_user" label="Quyền sở hữu" value="Chưa xác minh" />
        <DetailRow icon="star" label="Ưu tiên" value={entry.isPrimary ? "Xe chính" : "Xe phụ"} />
        <DetailRow icon="sync" label="Phiên bản dữ liệu" value={`${entry.version}`} last />
      </Surface>

      <Surface style={[styles.guardCard, { backgroundColor: theme.surfaceSubtle }]}>
        <AppIcon name="info" color={theme.accent} />
        <Text variant="caption" muted style={styles.grow}>
          Pin, vị trí, khóa cửa, điều hòa và sạc chưa xuất hiện vì garage entry này chưa phải bằng chứng sở hữu hay nguồn live vehicle authority.
        </Text>
      </Surface>
    </Screen>
  );
}

function DetailRow({
  icon,
  label,
  value,
  last = false,
}: {
  icon: string;
  label: string;
  value: string;
  last?: boolean;
}) {
  const theme = useCustomerTheme();
  return (
    <View style={[styles.detailRow, !last && { borderBottomColor: theme.border, borderBottomWidth: StyleSheet.hairlineWidth }]}>
      <AppIcon name={icon} color={theme.accent} size={21} />
      <Text muted style={styles.grow}>{label}</Text>
      <Text style={{ fontWeight: "600" }}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  hero: { minHeight: 300, borderRadius: 32, padding: 22, overflow: "hidden" },
  heroHeader: { flexDirection: "row", alignItems: "flex-start", gap: 12 },
  heroIcon: { width: 44, height: 44, borderRadius: 16, backgroundColor: "rgba(255,255,255,0.14)", alignItems: "center", justifyContent: "center" },
  grow: { flex: 1, gap: 3 },
  statusRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 12 },
  details: { paddingVertical: 4 },
  detailRow: { minHeight: 58, flexDirection: "row", alignItems: "center", gap: 12 },
  guardCard: { flexDirection: "row", alignItems: "flex-start", gap: 12 },
});
