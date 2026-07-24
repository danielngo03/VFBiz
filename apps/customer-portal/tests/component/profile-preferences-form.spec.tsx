import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ProfilePreferencesForm } from "@/features/account-profile/components/profile-preferences-form";

describe("ProfilePreferencesForm", () => {
  it("announces validation errors and submits normalized data", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn(async () => undefined);
    render(
      <ProfilePreferencesForm
        initialValue={{
          displayName: "",
          locale: "vi-VN",
          timezone: "Asia/Ho_Chi_Minh",
        }}
        onSubmit={onSubmit}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Lưu thay đổi" }));
    expect(
      await screen.findByText("Vui lòng nhập tên hiển thị."),
    ).toHaveAttribute("role", "alert");
    expect(onSubmit).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText("Tên hiển thị"), "  Anh Tuấn  ");
    await user.click(screen.getByRole("button", { name: "Lưu thay đổi" }));

    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith(
        {
          displayName: "Anh Tuấn",
          locale: "vi-VN",
          timezone: "Asia/Ho_Chi_Minh",
        },
        expect.anything(),
      ),
    );
  });
});
