import React from "react";
import { render, screen } from "@testing-library/react-native";
import { CustomerThemeProvider } from "../../src/design/theme/theme";
import { AccountScreen } from "../../src/features/account/account-screen";
import { GarageScreen } from "../../src/features/garage/garage-screen";
import { HomeScreen } from "../../src/features/home/home-screen";
import { useAuth } from "../../src/platform/auth/auth-context";
import { useConnectivity } from "../../src/platform/network/connectivity";
import {
  useCustomerGarage,
  useCustomerProfile,
} from "../../src/state/queries/customer-queries";

jest.mock("expo-router", () => ({ router: { push: jest.fn() } }));
jest.mock("../../src/platform/auth/auth-context", () => ({ useAuth: jest.fn() }));
jest.mock("../../src/platform/network/connectivity", () => ({
  useConnectivity: jest.fn(),
  resourceFreshness: jest.fn(() => "fresh"),
}));
jest.mock("../../src/state/queries/customer-queries", () => ({
  useCustomerGarage: jest.fn(),
  useCustomerProfile: jest.fn(),
}));

const profileResult = {
  data: { data: { displayName: "An Bình", market: "VN", locale: "vi" } },
  isLoading: false,
  isError: false,
  isStale: false,
};
const garageResult = {
  data: {
    data: [
      {
        id: "garage-001",
        nickname: "Mây Trắng",
        isPrimary: true,
        source: "self-reported",
        ownershipStatus: "unverified",
        status: "active",
      },
    ],
  },
  isLoading: false,
  isError: false,
  isStale: false,
};

beforeEach(() => {
  jest.mocked(useConnectivity).mockReturnValue("online");
  jest.mocked(useCustomerProfile).mockReturnValue(profileResult as never);
  jest.mocked(useCustomerGarage).mockReturnValue(garageResult as never);
  jest.mocked(useAuth).mockReturnValue({
    status: "authenticated",
    credential: { subject: "subject-001" },
    error: null,
    signIn: jest.fn(),
    refresh: jest.fn(),
    signOut: jest.fn(),
  } as never);
});

function renderScreen(element: React.ReactElement) {
  return render(<CustomerThemeProvider>{element}</CustomerThemeProvider>);
}

test("Home renders a truthful premium owner cockpit", () => {
  renderScreen(<HomeScreen />);
  expect(screen.getByText("An Bình")).toBeTruthy();
  expect(screen.getByText("Mây Trắng")).toBeTruthy();
  expect(screen.getByText("Chưa xác minh")).toBeTruthy();
  expect(screen.getByText("Truy cập nhanh")).toBeTruthy();
});

test("Garage distinguishes self-reporting from verified ownership", () => {
  renderScreen(<GarageScreen />);
  expect(screen.getByText("Garage")).toBeTruthy();
  expect(screen.getByText("Tự khai báo")).toBeTruthy();
  expect(screen.getByText("Thêm xe vào garage")).toBeTruthy();
});

test("Account exposes security and privacy controls", () => {
  renderScreen(<AccountScreen />);
  expect(screen.getByText("Tài khoản")).toBeTruthy();
  expect(screen.getByText("Bảo mật")).toBeTruthy();
  expect(screen.getByText("Quyền riêng tư")).toBeTruthy();
  expect(screen.getByText("Đăng xuất khỏi thiết bị này")).toBeTruthy();
});
