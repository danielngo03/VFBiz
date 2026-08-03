import { StyleSheet, View } from "react-native";
import { Avatar, InfoRow, LoadingState, ProblemState, Screen, StatusPill, Surface, Text } from "../../design/components";
import { useCustomerProfile } from "../../state/queries/customer-queries";

export function ProfileScreen() {
  const profile = useCustomerProfile();
  if (profile.isLoading) return <Screen><LoadingState label="Đang tải hồ sơ" /></Screen>;
  if (!profile.data) return <Screen><ProblemState title="Không có hồ sơ" detail="Dữ liệu chưa khả dụng." /></Screen>;
  const value = profile.data.data;
  const displayName = value.displayName || "Chưa đặt tên hiển thị";
  return (
    <Screen>
      <View style={styles.header}>
        <Avatar label={displayName} />
        <View style={styles.grow}>
          <Text variant="display">{displayName}</Text>
          <Text muted>Hồ sơ Customer của bạn</Text>
        </View>
      </View>
      <StatusPill state={profile.isStale ? "stale" : "fresh"} />
      <Surface style={styles.details}>
        <InfoRow icon="translate" label="Ngôn ngữ" value={value.locale === "vi" ? "Tiếng Việt" : "English"} />
        <InfoRow icon="public" label="Thị trường" value={value.market} />
        <InfoRow icon="schedule" label="Múi giờ" value={value.timezone} last />
      </Surface>
      <Surface>
        <Text variant="title">Kênh liên hệ</Text>
        <Text muted style={styles.topGap}>
          Email {value.communicationPreferences.email ? "đang bật" : "đang tắt"} · SMS {value.communicationPreferences.sms ? "đang bật" : "đang tắt"} · Push {value.communicationPreferences.push ? "đang bật" : "đang tắt"}
        </Text>
      </Surface>
      <Text variant="caption" muted style={styles.center}>
        Chỉnh sửa hồ sơ chỉ mở khi mutation ETag/If-Match hoàn tất kiểm thử xung đột end-to-end.
      </Text>
    </Screen>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", gap: 16, paddingTop: 8 },
  grow: { flex: 1, gap: 3 },
  details: { paddingVertical: 4 },
  topGap: { marginTop: 8 },
  center: { textAlign: "center" },
});
