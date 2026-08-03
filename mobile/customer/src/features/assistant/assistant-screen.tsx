import { StyleSheet, View } from "react-native";
import { AppIcon, Screen, Surface, Text } from "../../design/components";
import { useCustomerTheme } from "../../design/theme/theme";
import { runtimeConfig } from "../../platform/config/runtime-config";

export function AssistantScreen() {
  const theme = useCustomerTheme();
  return (
    <Screen>
      <View style={[styles.hero, { backgroundColor: theme.accentStrong }]}>
        <View style={styles.orb}><AppIcon name="auto_awesome" size={42} color={theme.onAccent} /></View>
        <Text variant="caption" style={{ color: `${theme.onAccent}AD` }}>VIVI ASSISTANT</Text>
        <Text variant="display" style={{ color: theme.onAccent }}>Thông minh hơn, nhưng luôn có giới hạn rõ ràng.</Text>
      </View>
      <Surface style={styles.card}>
        <View style={[styles.lock, { backgroundColor: theme.surfaceSubtle }]}><AppIcon name="lock" color={theme.accent} /></View>
        <View style={styles.grow}>
          <Text variant="title">{runtimeConfig.assistantEnabled ? "Đang chờ capability" : "Chưa được bật"}</Text>
          <Text muted>ViVi chỉ hoạt động khi API authority cấp capability. Mobile không gọi model hoặc AI Platform trực tiếp.</Text>
        </View>
      </Surface>
      <Text variant="caption" muted style={styles.center}>Không dùng AI response làm bằng chứng cho quyền sở hữu, trạng thái xe hay quyết định an toàn.</Text>
    </Screen>
  );
}

const styles = StyleSheet.create({
  hero: { minHeight: 330, borderRadius: 34, padding: 26, justifyContent: "flex-end", gap: 12, overflow: "hidden" },
  orb: { width: 76, height: 76, borderRadius: 38, backgroundColor: "rgba(255,255,255,0.13)", alignItems: "center", justifyContent: "center" },
  card: { flexDirection: "row", alignItems: "flex-start", gap: 14 },
  lock: { width: 50, height: 50, borderRadius: 17, alignItems: "center", justifyContent: "center" },
  grow: { flex: 1, gap: 5 },
  center: { textAlign: "center" },
});
