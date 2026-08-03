import React from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text as NativeText,
  TextInput,
  Switch,
  View,
  type PressableProps,
  type ColorValue,
  type TextProps,
  type ViewProps,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import type { FreshnessState } from "../../domain/freshness/freshness";
import { freshnessDescriptors } from "../../domain/freshness/freshness";
import { nativePrimitives, useCustomerTheme } from "../theme/theme";

export function Screen({
  children,
  scroll = true,
  ...props
}: React.PropsWithChildren<ViewProps & { scroll?: boolean }>) {
  const theme = useCustomerTheme();
  const content = <View style={styles.screenContent}>{children}</View>;
  return (
    <SafeAreaView
      edges={["top", "left", "right"]}
      style={[styles.safeArea, { backgroundColor: theme.canvas }]}
      {...props}
    >
      {scroll ? (
        <ScrollView
          contentContainerStyle={styles.scrollContent}
          showsVerticalScrollIndicator={false}
        >
          {content}
        </ScrollView>
      ) : (
        content
      )}
    </SafeAreaView>
  );
}

export function Surface({ children, style, ...props }: ViewProps) {
  const theme = useCustomerTheme();
  return (
    <View
      style={[
        styles.surface,
        { backgroundColor: theme.surface, borderColor: theme.border },
        style,
      ]}
      {...props}
    >
      {children}
    </View>
  );
}

export function AppIcon({
  name,
  size = 24,
  color,
}: {
  name: string;
  size?: number;
  color?: ColorValue;
}) {
  const theme = useCustomerTheme();
  return (
    <NativeText
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={{
        color: color ?? theme.text,
        fontFamily: "MaterialSymbols",
        fontSize: size,
        lineHeight: size + 4,
      }}
    >
      {name}
    </NativeText>
  );
}

export function Avatar({ label }: { label: string }) {
  const theme = useCustomerTheme();
  const initials = label
    .split(/\s+/u)
    .filter(Boolean)
    .slice(-2)
    .map((part) => part[0]?.toUpperCase())
    .join("") || "VF";
  return (
    <View
      accessibilityLabel={`Tài khoản ${label}`}
      style={[styles.avatar, { backgroundColor: theme.accent }]}
    >
      <Text style={{ color: theme.onAccent, fontWeight: "700" }}>{initials}</Text>
    </View>
  );
}

export function SectionHeader({
  title,
  actionLabel,
  onAction,
}: {
  title: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <View style={styles.sectionHeader}>
      <Text variant="title">{title}</Text>
      {actionLabel && onAction ? (
        <Pressable accessibilityRole="button" onPress={onAction} hitSlop={8}>
          <Text variant="caption" style={{ fontWeight: "700" }}>{actionLabel}</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

export function InfoRow({
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
    <View
      style={[
        styles.infoRow,
        !last && {
          borderBottomColor: theme.border,
          borderBottomWidth: StyleSheet.hairlineWidth,
        },
      ]}
    >
      <View style={[styles.infoIcon, { backgroundColor: theme.surfaceSubtle }]}>
        <AppIcon name={icon} color={theme.accent} size={20} />
      </View>
      <Text muted style={styles.grow}>{label}</Text>
      <Text style={styles.infoValue}>{value}</Text>
    </View>
  );
}

export function QuickAction({
  icon,
  label,
  detail,
  onPress,
  disabled = false,
}: {
  icon: string;
  label: string;
  detail?: string;
  onPress: () => void;
  disabled?: boolean;
}) {
  const theme = useCustomerTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled }}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.quickAction,
        {
          backgroundColor: theme.surface,
          borderColor: theme.border,
          opacity: disabled ? 0.45 : pressed ? 0.72 : 1,
        },
      ]}
    >
      <View style={[styles.quickActionIcon, { backgroundColor: theme.surfaceSubtle }]}>
        <AppIcon name={icon} color={theme.accent} />
      </View>
      <Text style={{ fontWeight: "600" }}>{label}</Text>
      {detail ? <Text variant="caption" muted>{detail}</Text> : null}
    </Pressable>
  );
}

export function VehicleSilhouette({ compact = false }: { compact?: boolean }) {
  const theme = useCustomerTheme();
  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={[styles.vehicleStage, compact && styles.vehicleStageCompact]}
    >
      <View style={[styles.vehicleRoof, { backgroundColor: `${theme.onAccent}47` }]} />
      <View style={[styles.vehicleBody, { backgroundColor: `${theme.onAccent}E0` }]} />
      <View style={[styles.vehicleWheel, styles.vehicleWheelLeft, { borderColor: theme.onAccent, backgroundColor: theme.accentStrong }]} />
      <View style={[styles.vehicleWheel, styles.vehicleWheelRight, { borderColor: theme.onAccent, backgroundColor: theme.accentStrong }]} />
    </View>
  );
}

export function Text({
  variant = "body",
  muted = false,
  style,
  ...props
}: TextProps & {
  variant?: "caption" | "body" | "title" | "display";
  muted?: boolean;
}) {
  const theme = useCustomerTheme();
  return (
    <NativeText
      allowFontScaling
      maxFontSizeMultiplier={2}
      style={[
        {
          color: muted ? theme.textMuted : theme.text,
          fontSize: nativePrimitives.fontSize[variant],
          lineHeight: nativePrimitives.lineHeight[variant],
          fontWeight:
            variant === "display" ? "700" : variant === "title" ? "600" : "400",
        },
        style,
      ]}
      {...props}
    />
  );
}

export function Button({
  label,
  tone = "primary",
  disabled,
  style,
  ...props
}: PressableProps & {
  label: string;
  tone?: "primary" | "secondary" | "danger";
}) {
  const theme = useCustomerTheme();
  const backgroundColor =
    tone === "primary" ? theme.accent : tone === "danger" ? theme.danger : theme.surfaceSubtle;
  const color = tone === "secondary" ? theme.text : theme.onAccent;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: Boolean(disabled) }}
      disabled={disabled}
      style={(state) => [
        styles.button,
        {
          backgroundColor,
          opacity: disabled ? 0.45 : state.pressed ? 0.78 : 1,
        },
        typeof style === "function" ? style(state) : style,
      ]}
      {...props}
    >
      <Text style={{ color, fontWeight: "600" }}>{label}</Text>
    </Pressable>
  );
}

export function IconButton({
  label,
  symbol,
  ...props
}: PressableProps & { label: string; symbol: string }) {
  const theme = useCustomerTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      hitSlop={8}
      style={({ pressed }) => [
        styles.iconButton,
        { backgroundColor: theme.surfaceSubtle, opacity: pressed ? 0.7 : 1 },
      ]}
      {...props}
    >
      <Text accessibilityElementsHidden>{symbol}</Text>
    </Pressable>
  );
}

export function TextField({
  label,
  value,
  onChangeText,
  placeholder,
}: {
  label: string;
  value: string;
  onChangeText: (value: string) => void;
  placeholder?: string;
}) {
  const theme = useCustomerTheme();
  return (
    <View style={styles.field}>
      <Text variant="caption" muted>{label}</Text>
      <TextInput
        accessibilityLabel={label}
        allowFontScaling
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor={theme.textMuted}
        style={[
          styles.input,
          {
            backgroundColor: theme.surfaceSubtle,
            borderColor: theme.border,
            color: theme.text,
          },
        ]}
      />
    </View>
  );
}

export function ToggleRow({
  title,
  detail,
  value,
  onValueChange,
}: {
  title: string;
  detail?: string;
  value: boolean;
  onValueChange: (value: boolean) => void;
}) {
  const theme = useCustomerTheme();
  return (
    <View style={styles.toggleRow}>
      <View style={styles.grow}>
        <Text>{title}</Text>
        {detail ? <Text variant="caption" muted>{detail}</Text> : null}
      </View>
      <Switch
        accessibilityLabel={title}
        value={value}
        onValueChange={onValueChange}
        trackColor={{ false: theme.border, true: theme.accent }}
      />
    </View>
  );
}

export function ListRow({
  icon,
  title,
  detail,
  trailing = "›",
  onPress,
}: {
  icon?: string;
  title: string;
  detail?: string;
  trailing?: string;
  onPress?: () => void;
}) {
  const theme = useCustomerTheme();
  return (
    <Pressable
      accessibilityRole={onPress ? "button" : "text"}
      onPress={onPress}
      style={({ pressed }) => [
        styles.listRow,
        { borderBottomColor: theme.border, opacity: pressed ? 0.65 : 1 },
      ]}
    >
      {icon ? (
        <View style={[styles.listIcon, { backgroundColor: theme.surfaceSubtle }]}>
          <AppIcon name={icon} color={theme.accent} size={21} />
        </View>
      ) : null}
      <View style={styles.grow}>
        <Text>{title}</Text>
        {detail ? <Text variant="caption" muted>{detail}</Text> : null}
      </View>
      <Text muted accessibilityElementsHidden>{trailing}</Text>
    </Pressable>
  );
}

export function StatusPill({ state }: { state: FreshnessState }) {
  const theme = useCustomerTheme();
  const descriptor = freshnessDescriptors[state];
  const backgroundColor =
    descriptor.tone === "positive"
      ? `${theme.accent}22`
      : descriptor.tone === "danger"
        ? `${theme.danger}22`
        : theme.surfaceSubtle;
  return (
    <View
      accessibilityRole="text"
      accessibilityLabel={`Trạng thái: ${descriptor.label}`}
      style={[styles.pill, { backgroundColor }]}
    >
      <Text variant="caption">{descriptor.label}</Text>
    </View>
  );
}

export function EmptyState({ title, detail }: { title: string; detail: string }) {
  return <StateMessage symbol="◇" title={title} detail={detail} />;
}

export function ProblemState({ title, detail }: { title: string; detail: string }) {
  return <StateMessage symbol="!" title={title} detail={detail} />;
}

export function LoadingState({ label = "Đang tải" }: { label?: string }) {
  const theme = useCustomerTheme();
  return (
    <View accessibilityRole="progressbar" accessibilityLabel={label} style={styles.state}>
      <ActivityIndicator color={theme.accent} />
      <Text muted>{label}</Text>
    </View>
  );
}

export function BottomTabs({ children }: React.PropsWithChildren) {
  const theme = useCustomerTheme();
  return (
    <View style={[styles.bottomTabs, { backgroundColor: theme.surface, borderColor: theme.border }]}>
      {children}
    </View>
  );
}

function StateMessage({ symbol, title, detail }: { symbol: string; title: string; detail: string }) {
  return (
    <View style={styles.state}>
      <Text variant="display" accessibilityElementsHidden>{symbol}</Text>
      <Text variant="title">{title}</Text>
      <Text muted style={styles.center}>{detail}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1 },
  scrollContent: { flexGrow: 1 },
  screenContent: { flex: 1, width: "100%", maxWidth: 720, alignSelf: "center", gap: 20, paddingHorizontal: 20, paddingBottom: 40 },
  surface: { borderRadius: 24, borderWidth: StyleSheet.hairlineWidth, padding: 18, shadowColor: "#000000", shadowOpacity: 0.04, shadowRadius: 18, shadowOffset: { width: 0, height: 8 }, elevation: 1 },
  button: { minHeight: 48, borderRadius: 16, alignItems: "center", justifyContent: "center", paddingHorizontal: 20 },
  iconButton: { width: 48, height: 48, borderRadius: 24, alignItems: "center", justifyContent: "center" },
  listRow: { minHeight: 56, flexDirection: "row", alignItems: "center", gap: 12, borderBottomWidth: StyleSheet.hairlineWidth, paddingVertical: 10 },
  listIcon: { width: 42, height: 42, borderRadius: 14, alignItems: "center", justifyContent: "center" },
  grow: { flex: 1, gap: 2 },
  pill: { alignSelf: "flex-start", borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5 },
  state: { flex: 1, minHeight: 220, alignItems: "center", justifyContent: "center", gap: 10, padding: 24 },
  center: { textAlign: "center" },
  bottomTabs: { minHeight: 64, flexDirection: "row", borderTopWidth: StyleSheet.hairlineWidth },
  field: { gap: 6 },
  input: { minHeight: 48, borderWidth: StyleSheet.hairlineWidth, borderRadius: 14, paddingHorizontal: 14, fontSize: 16 },
  toggleRow: { minHeight: 64, flexDirection: "row", alignItems: "center", gap: 16, paddingVertical: 8 },
  avatar: { width: 48, height: 48, borderRadius: 24, alignItems: "center", justifyContent: "center" },
  sectionHeader: { minHeight: 32, flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 16 },
  quickAction: { flexBasis: "47%", flexGrow: 1, minHeight: 132, borderRadius: 22, borderWidth: StyleSheet.hairlineWidth, padding: 16, gap: 8 },
  quickActionIcon: { width: 44, height: 44, borderRadius: 14, alignItems: "center", justifyContent: "center", marginBottom: 2 },
  infoRow: { minHeight: 64, flexDirection: "row", alignItems: "center", gap: 12 },
  infoIcon: { width: 38, height: 38, borderRadius: 12, alignItems: "center", justifyContent: "center" },
  infoValue: { maxWidth: "48%", textAlign: "right", fontWeight: "600" },
  vehicleStage: { height: 126, marginTop: 8, justifyContent: "flex-end", alignItems: "center" },
  vehicleStageCompact: { height: 80, transform: [{ scale: 0.72 }] },
  vehicleRoof: { position: "absolute", bottom: 38, width: 154, height: 46, borderTopLeftRadius: 56, borderTopRightRadius: 56, transform: [{ skewX: "-8deg" }] },
  vehicleBody: { width: 240, height: 56, borderTopLeftRadius: 44, borderTopRightRadius: 36, borderBottomLeftRadius: 22, borderBottomRightRadius: 22 },
  vehicleWheel: { position: "absolute", bottom: -9, width: 34, height: 34, borderRadius: 17, borderWidth: 7 },
  vehicleWheelLeft: { left: "24%" },
  vehicleWheelRight: { right: "24%" },
});
