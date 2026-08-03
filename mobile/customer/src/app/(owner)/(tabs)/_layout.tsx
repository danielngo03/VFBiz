import { Tabs } from "expo-router";
import { useCustomerTheme } from "../../../design/theme/theme";
import { AppIcon } from "../../../design/components";

export default function OwnerTabsLayout() {
  const theme = useCustomerTheme();
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: theme.accent,
        tabBarInactiveTintColor: theme.textMuted,
        tabBarStyle: {
          backgroundColor: theme.surface,
          borderTopColor: theme.border,
          height: 76,
          paddingTop: 8,
          paddingBottom: 10,
        },
        tabBarLabelStyle: { fontSize: 11, fontWeight: "600" },
        tabBarHideOnKeyboard: true,
      }}
    >
      <Tabs.Screen name="index" options={{ title: "Trang chủ", tabBarAccessibilityLabel: "Trang chủ", tabBarIcon: ({ color, size }) => <AppIcon name="home" color={color} size={size} /> }} />
      <Tabs.Screen name="garage" options={{ title: "Garage", tabBarAccessibilityLabel: "Garage", tabBarIcon: ({ color, size }) => <AppIcon name="directions_car" color={color} size={size} /> }} />
      <Tabs.Screen name="account" options={{ title: "Tài khoản", tabBarAccessibilityLabel: "Tài khoản", tabBarIcon: ({ color, size }) => <AppIcon name="person" color={color} size={size} /> }} />
    </Tabs>
  );
}
