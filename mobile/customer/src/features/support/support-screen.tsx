import { StyleSheet, View } from "react-native";
import { AppIcon, Screen, Surface, Text } from "../../design/components";
import { useCustomerTheme } from "../../design/theme/theme";

export function SupportScreen() {
  const theme = useCustomerTheme();
  return (
    <Screen>
      <View style={[styles.hero, { backgroundColor: theme.accentStrong }]}>
        <View style={styles.icon}><AppIcon name="support_agent" color={theme.onAccent} size={36} /></View>
        <Text variant="display" style={{ color: theme.onAccent }}>Chúng tôi ở đây để hỗ trợ</Text>
        <Text style={{ color: `${theme.onAccent}C2` }}>Kênh liên hệ chỉ được mở khi số điện thoại, giờ hoạt động, thị trường và SLA có source authority.</Text>
      </View>
      <Surface style={styles.card}>
        <AppIcon name="schedule" color={theme.accent} />
        <View style={styles.grow}>
          <Text variant="title">Kênh hỗ trợ đang được xác nhận</Text>
          <Text muted>App chưa hiển thị số điện thoại hoặc cam kết phản hồi chưa được phê duyệt.</Text>
        </View>
      </Surface>
      <Surface style={[styles.card, { backgroundColor: theme.surfaceSubtle }]}>
        <AppIcon name="emergency" color={theme.danger} />
        <Text variant="caption" muted style={styles.grow}>Đây chưa phải kênh khẩn cấp hoặc roadside assistance. Không dựa vào màn hình này cho tình huống an toàn.</Text>
      </Surface>
    </Screen>
  );
}

const styles = StyleSheet.create({
  hero: { minHeight: 290, borderRadius: 32, padding: 24, justifyContent: "flex-end", gap: 12, overflow: "hidden" },
  icon: { width: 62, height: 62, borderRadius: 22, backgroundColor: "rgba(255,255,255,0.13)", alignItems: "center", justifyContent: "center" },
  card: { flexDirection: "row", alignItems: "flex-start", gap: 14 },
  grow: { flex: 1, gap: 5 },
});
