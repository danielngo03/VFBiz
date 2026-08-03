import { readFileSync } from "node:fs";
import path from "node:path";

test("Expo Router declarations contain Customer routes", () => {
  const declaration = readFileSync(
    path.resolve(".expo/types/router.d.ts"),
    "utf8",
  );
  expect(declaration).toContain("/sign-in");
  expect(declaration).toContain("/garage/[garageEntryId]");
  expect(declaration).toContain("/account/profile");
});
