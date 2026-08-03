import { render, screen } from "@testing-library/react-native";
import { StatusPill } from "../../src/design/components";
import { CustomerThemeProvider } from "../../src/design/theme/theme";

test("status pill exposes semantic accessibility label", () => {
  render(<StatusPill state="offline" />, { wrapper: CustomerThemeProvider });
  expect(screen.getByLabelText("Trạng thái: Đang ngoại tuyến")).toBeOnTheScreen();
});
