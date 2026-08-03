import { QueryClientProvider } from "@tanstack/react-query";
import { MaterialSymbols_400Regular } from "@expo-google-fonts/material-symbols/400Regular";
import { useFonts } from "expo-font";
import { Stack } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { StatusBar } from "expo-status-bar";
import { useEffect, useMemo } from "react";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { CustomerThemeProvider, useCustomerTheme } from "../design/theme/theme";
import { AuthProvider } from "../platform/auth/auth-context";
import { createCustomerQueryClient } from "../state/hydration/query-client";

void SplashScreen.preventAutoHideAsync();

export default function RootLayout() {
  const queryClient = useMemo(() => createCustomerQueryClient(), []);
  const [fontsLoaded, fontError] = useFonts({
    MaterialSymbols: MaterialSymbols_400Regular,
  });
  useEffect(() => {
    if (fontsLoaded || fontError) void SplashScreen.hideAsync();
  }, [fontError, fontsLoaded]);
  if (!fontsLoaded && !fontError) return null;
  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <QueryClientProvider client={queryClient}>
        <CustomerThemeProvider>
          <AuthProvider queryClient={queryClient}>
            <RootNavigator />
          </AuthProvider>
        </CustomerThemeProvider>
      </QueryClientProvider>
    </GestureHandlerRootView>
  );
}

function RootNavigator() {
  const theme = useCustomerTheme();
  return (
    <>
      <StatusBar style={theme.mode === "dark" ? "light" : "dark"} />
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: theme.canvas },
          headerTintColor: theme.text,
          headerShadowVisible: false,
          contentStyle: { backgroundColor: theme.canvas },
          animation: "fade_from_bottom",
        }}
      >
        <Stack.Screen name="index" options={{ headerShown: false }} />
        <Stack.Screen name="sign-in" options={{ headerShown: false }} />
        <Stack.Screen name="auth/callback" options={{ headerShown: false }} />
        <Stack.Screen name="(owner)" options={{ headerShown: false }} />
      </Stack>
    </>
  );
}
