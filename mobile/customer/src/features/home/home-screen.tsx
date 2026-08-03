import { router } from "expo-router";
import { Pressable, StyleSheet, View } from "react-native";
import {
  AppIcon,
  Avatar,
  LoadingState,
  ProblemState,
  QuickAction,
  Screen,
  SectionHeader,
  StatusPill,
  Surface,
  Text,
  VehicleSilhouette,
} from "../../design/components";
import { useCustomerTheme } from "../../design/theme/theme";
import { runtimeConfig } from "../../platform/config/runtime-config";
import {
  resourceFreshness,
  useConnectivity,
} from "../../platform/network/connectivity";
import {
  useCustomerGarage,
  useCustomerProfile,
} from "../../state/queries/customer-queries";

export function HomeScreen() {
  const theme = useCustomerTheme();
  const profile = useCustomerProfile();
  const garage = useCustomerGarage();
  const connectivity = useConnectivity();
  const hasData = Boolean(profile.data || garage.data);
  if ((profile.isLoading || garage.isLoading) && !hasData)
    return <Screen><LoadingState label="Đang chuẩn bị không gian của bạn" /></Screen>;
  if (profile.isError && garage.isError && !hasData)
    return <Screen><ProblemState title="Chưa tải được trang chủ" detail="Kiểm tra kết nối hoặc đăng nhập lại." /></Screen>;

  const displayName = profile.data?.data.displayName?.trim() || "Chủ xe VFBiz";
  const entries = garage.data?.data ?? [];
  const primaryVehicle = entries.find((entry) => entry.isPrimary) ?? entries[0];
  const freshness = resourceFreshness({
    connectivity,
    hasData,
    stale: profile.isStale || garage.isStale,
    error: profile.isError || garage.isError,
  });

  return (
    <Screen>
      <View style={styles.header}>
        <View style={styles.grow}>
          <Text variant="caption" muted>CHÀO MỪNG TRỞ LẠI</Text>
          <Text variant="display" numberOfLines={2}>{displayName}</Text>
        </View>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Mở tài khoản"
          onPress={() => router.push("/(owner)/(tabs)/account")}
        >
          <Avatar label={displayName} />
        </Pressable>
      </View>

      <View style={styles.statusRow}>
        <StatusPill state={freshness} />
        <Text variant="caption" muted>{entries.length} xe trong garage</Text>
      </View>

      <Pressable
        accessibilityRole="button"
        accessibilityLabel={primaryVehicle ? `Mở xe ${primaryVehicle.nickname ?? "của tôi"}` : "Thêm xe vào garage"}
        onPress={() =>
          primaryVehicle
            ? router.push({ pathname: "/(owner)/garage/[garageEntryId]", params: { garageEntryId: primaryVehicle.id } })
            : router.push("/(owner)/garage/add")
        }
        style={({ pressed }) => [
          styles.vehicleCard,
          { backgroundColor: theme.accentStrong, opacity: pressed ? 0.92 : 1 },
        ]}
      >
        <View style={styles.vehicleCardHeader}>
          <View style={styles.grow}>
            <Text variant="caption" style={{ color: `${theme.onAccent}AD` }}>XE ĐƯỢC ƯU TIÊN</Text>
            <Text variant="title" style={{ color: theme.onAccent }}>
              {primaryVehicle?.nickname ?? "Thêm chiếc xe đầu tiên"}
            </Text>
          </View>
          <View style={styles.roundControl}>
            <AppIcon name="arrow_forward" color={theme.onAccent} size={20} />
          </View>
        </View>
        <VehicleSilhouette />
        <View style={styles.vehicleFooter}>
          <View>
            <Text variant="caption" style={{ color: `${theme.onAccent}AD` }}>QUYỀN SỞ HỮU</Text>
            <Text style={{ color: theme.onAccent }}>Chưa xác minh</Text>
          </View>
          <View style={styles.divider} />
          <View style={styles.grow}>
            <Text variant="caption" style={{ color: `${theme.onAccent}AD` }}>NGUỒN DỮ LIỆU</Text>
            <Text style={{ color: theme.onAccent }}>Tự khai báo</Text>
          </View>
        </View>
      </Pressable>

      <SectionHeader title="Truy cập nhanh" />
      <View style={styles.actions}>
        <QuickAction icon="directions_car" label="Garage" detail="Quản lý xe" onPress={() => router.push("/(owner)/(tabs)/garage")} />
        <QuickAction icon="shield_person" label="Bảo mật" detail="Phiên & MFA" onPress={() => router.push("/(owner)/account/security")} />
        <QuickAction icon="support_agent" label="Hỗ trợ" detail="Kênh chính thức" onPress={() => router.push("/(owner)/support")} />
        <QuickAction icon="auto_awesome" label="ViVi" detail={runtimeConfig.assistantEnabled ? "Trợ lý của bạn" : "Sắp ra mắt"} disabled={!runtimeConfig.assistantEnabled} onPress={() => router.push("/(owner)/assistant")} />
      </View>

      <SectionHeader title="Quyền kiểm soát của bạn" actionLabel="Xem tài khoản" onAction={() => router.push("/(owner)/(tabs)/account")} />
      <Surface style={styles.controlCard}>
        <View style={[styles.controlIcon, { backgroundColor: theme.surfaceSubtle }]}>
          <AppIcon name="verified_user" color={theme.accent} />
        </View>
        <View style={styles.grow}>
          <Text style={{ fontWeight: "600" }}>Dữ liệu rõ ràng, quyền hạn minh bạch</Text>
          <Text variant="caption" muted>
            Hồ sơ, phiên đăng nhập và đồng thuận đều có nguồn dữ liệu thật. Điều khiển xe chỉ xuất hiện khi backend xác thực capability.
          </Text>
        </View>
      </Surface>
    </Screen>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", gap: 16, paddingTop: 8 },
  grow: { flex: 1, gap: 3 },
  statusRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 12 },
  vehicleCard: { minHeight: 330, borderRadius: 32, padding: 22, overflow: "hidden", shadowColor: "#071410", shadowOpacity: 0.24, shadowRadius: 24, shadowOffset: { width: 0, height: 14 }, elevation: 8 },
  vehicleCardHeader: { flexDirection: "row", alignItems: "flex-start", gap: 12 },
  roundControl: { width: 42, height: 42, borderRadius: 21, alignItems: "center", justifyContent: "center", backgroundColor: "rgba(255,255,255,0.14)" },
  vehicleFooter: { flexDirection: "row", alignItems: "center", gap: 18, paddingTop: 22 },
  divider: { width: StyleSheet.hairlineWidth, height: 34, backgroundColor: "rgba(255,255,255,0.24)" },
  actions: { flexDirection: "row", flexWrap: "wrap", gap: 12 },
  controlCard: { flexDirection: "row", alignItems: "center", gap: 14 },
  controlIcon: { width: 48, height: 48, borderRadius: 16, alignItems: "center", justifyContent: "center" },
});
