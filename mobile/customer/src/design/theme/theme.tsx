import { nativeTokens } from "@vfbiz/design-tokens/native";
import React, { createContext, useContext, useMemo } from "react";
import { useColorScheme } from "react-native";

export interface CustomerTheme {
  surface: string;
  surfaceSubtle: string;
  text: string;
  textMuted: string;
  border: string;
  danger: string;
  focus: string;
  radiusSmall: number;
  radiusMedium: number;
  radiusLarge: number;
  accent: string;
  accentStrong: string;
  onAccent: string;
  canvas: string;
  mode: "light" | "dark";
}

const ThemeContext = createContext<CustomerTheme | null>(null);

export function CustomerThemeProvider({ children }: React.PropsWithChildren) {
  const scheme = useColorScheme();
  const value = useMemo<CustomerTheme>(
    () => ({
      ...(scheme === "dark"
        ? nativeTokens.customer.dark
        : nativeTokens.customer.light),
      mode: scheme === "dark" ? ("dark" as const) : ("light" as const),
    }),
    [scheme],
  );
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useCustomerTheme(): CustomerTheme {
  const context = useContext(ThemeContext);
  if (!context)
    throw new Error("useCustomerTheme must be used within CustomerThemeProvider.");
  return context;
}

export const nativePrimitives = nativeTokens.primitive;
