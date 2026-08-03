import { Redirect } from "expo-router";
import { StyleSheet, View } from "react-native";
import {
  AppIcon,
  Button,
  ProblemState,
  Screen,
  Surface,
  Text,
} from "../design/components";
import { useCustomerTheme } from "../design/theme/theme";
import { useAuth } from "../platform/auth/auth-context";

export default function SignInRoute() {
  const theme = useCustomerTheme();
  const auth = useAuth();
  if (auth.credential) return <Redirect href="/(owner)/(tabs)" />;
  return (
    <Screen>
      <View style={styles.brandRow}>
        <View style={[styles.brandMark, { backgroundColor: theme.accent }]}>
          <AppIcon name="electric_car" color={theme.onAccent} size={26} />
        </View>
        <View>
          <Text style={{ fontWeight: "700" }}>VFBiz</Text>
          <Text variant="caption" muted>Customer</Text>
        </View>
      </View>

      <View style={[styles.hero, { backgroundColor: theme.accentStrong }]}>
        <View style={styles.heroOrbLarge} />
        <View style={styles.heroOrbSmall} />
        <View style={styles.heroContent}>
          <Text variant="caption" style={{ color: `${theme.onAccent}C2` }}>KHÔNG GIAN CHỦ XE</Text>
          <Text variant="display" style={{ color: theme.onAccent }}>
            Mọi điều quan trọng, thật rõ ràng.
          </Text>
          <Text style={{ color: `${theme.onAccent}C2` }}>
            Một nơi an toàn để quản lý hồ sơ, garage, phiên đăng nhập và quyền riêng tư của bạn.
          </Text>
        </View>
      </View>

      <Surface style={styles.signInCard}>
        {auth.status === "error" && auth.error ? (
          <ProblemState title="Đăng nhập chưa hoàn tất" detail={auth.error} />
        ) : null}
        <View style={styles.assuranceRow}>
          <View style={[styles.assuranceIcon, { backgroundColor: theme.surfaceSubtle }]}>
            <AppIcon name="shield_lock" color={theme.accent} />
          </View>
          <View style={styles.grow}>
            <Text style={{ fontWeight: "600" }}>Đăng nhập bảo mật</Text>
            <Text variant="caption" muted>Mật khẩu và MFA chỉ xuất hiện trong trình duyệt hệ thống.</Text>
          </View>
        </View>
        <Button
          label={auth.status === "authenticating" ? "Đang mở đăng nhập…" : "Tiếp tục đăng nhập"}
          disabled={auth.status === "authenticating"}
          onPress={() => void auth.signIn()}
        />
        <Text variant="caption" muted style={styles.center}>
          Bằng việc tiếp tục, bạn sử dụng phiên đăng nhập Customer được bảo vệ bằng PKCE.
        </Text>
      </Surface>
    </Screen>
  );
}

const styles = StyleSheet.create({
  brandRow: { flexDirection: "row", alignItems: "center", gap: 10, paddingTop: 8 },
  brandMark: { width: 44, height: 44, borderRadius: 15, alignItems: "center", justifyContent: "center" },
  hero: { minHeight: 330, borderRadius: 34, padding: 26, overflow: "hidden", justifyContent: "flex-end" },
  heroContent: { maxWidth: 460, gap: 12, zIndex: 2 },
  heroOrbLarge: { position: "absolute", width: 260, height: 260, borderRadius: 130, right: -80, top: -70, backgroundColor: "rgba(255,255,255,0.08)" },
  heroOrbSmall: { position: "absolute", width: 120, height: 120, borderRadius: 60, right: 52, top: 88, borderWidth: 22, borderColor: "rgba(255,255,255,0.09)" },
  signInCard: { gap: 18 },
  assuranceRow: { flexDirection: "row", alignItems: "center", gap: 12 },
  assuranceIcon: { width: 48, height: 48, borderRadius: 16, alignItems: "center", justifyContent: "center" },
  grow: { flex: 1, gap: 2 },
  center: { textAlign: "center" },
});
