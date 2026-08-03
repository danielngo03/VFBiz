import { router } from "expo-router";
import { Pressable, StyleSheet, View } from "react-native";
import {
  AppIcon,
  Avatar,
  Button,
  ListRow,
  Screen,
  StatusPill,
  Surface,
  Text,
} from "../../design/components";
import { useCustomerTheme } from "../../design/theme/theme";
import { useAuth } from "../../platform/auth/auth-context";
import { useConnectivity } from "../../platform/network/connectivity";
import { useCustomerProfile } from "../../state/queries/customer-queries";

export function AccountScreen() {
  const theme = useCustomerTheme();
  const auth = useAuth();
  const profile = useCustomerProfile();
  const connectivity = useConnectivity();
  const displayName = profile.data?.data.displayName?.trim() || "Chủ xe VFBiz";
  const market = profile.data?.data.market ?? "VN";
  const locale = profile.data?.data.locale === "en" ? "English" : "Tiếng Việt";
  const state = connectivity === "offline"
    ? "offline"
    : connectivity === "unknown"
      ? "unknown"
      : auth.credential
        ? "fresh"
        : "restricted";

  return (
    <Screen>
      <View style={styles.titleRow}>
        <View style={styles.grow}>
          <Text variant="caption" muted>TRUNG TÂM CÁ NHÂN</Text>
          <Text variant="display">Tài khoản</Text>
        </View>
        <StatusPill state={state} />
      </View>

      <Surface style={styles.identityCard}>
        <Avatar label={displayName} />
        <View style={styles.grow}>
          <Text variant="title">{displayName}</Text>
          <Text variant="caption" muted>{market} · {locale}</Text>
        </View>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Chỉnh sửa hồ sơ"
          hitSlop={8}
          onPress={() => router.push("/(owner)/account/profile")}
        >
          <AppIcon name="edit" color={theme.textMuted} size={21} />
        </Pressable>
      </Surface>

      <View style={styles.sectionLabel}>
        <Text variant="caption" muted>THÔNG TIN & BẢO MẬT</Text>
      </View>
      <Surface style={styles.menuCard}>
        <ListRow icon="person" title="Hồ sơ" detail="Tên hiển thị, ngôn ngữ và thị trường" onPress={() => router.push("/(owner)/account/profile")} />
        <ListRow icon="shield_lock" title="Bảo mật" detail="Trạng thái xác minh và MFA" onPress={() => router.push("/(owner)/account/security")} />
        <ListRow icon="devices" title="Phiên đăng nhập" detail="Thiết bị và hoạt động gần đây" onPress={() => router.push("/(owner)/account/sessions")} />
      </Surface>

      <View style={styles.sectionLabel}>
        <Text variant="caption" muted>QUYỀN KIỂM SOÁT DỮ LIỆU</Text>
      </View>
      <Surface style={styles.menuCard}>
        <ListRow icon="privacy_tip" title="Quyền riêng tư" detail="Xuất hoặc xóa dữ liệu" onPress={() => router.push("/(owner)/account/privacy")} />
        <ListRow icon="fact_check" title="Đồng thuận" detail="Mục đích và phiên bản chính sách" onPress={() => router.push("/(owner)/account/consents")} />
      </Surface>

      <Button label="Đăng xuất khỏi thiết bị này" tone="secondary" onPress={() => void auth.signOut()} />
      <Text variant="caption" muted style={styles.footnote}>
        Đăng xuất sẽ xóa credential, cache, dữ liệu ngoại tuyến và hàng đợi chưa đồng bộ trên thiết bị này.
      </Text>
    </Screen>
  );
}

const styles = StyleSheet.create({
  titleRow: { flexDirection: "row", alignItems: "center", gap: 16, paddingTop: 8 },
  grow: { flex: 1, gap: 3 },
  identityCard: { flexDirection: "row", alignItems: "center", gap: 14, paddingVertical: 20 },
  sectionLabel: { paddingHorizontal: 4, marginBottom: -10 },
  menuCard: { paddingVertical: 4 },
  footnote: { textAlign: "center", paddingHorizontal: 18 },
});
