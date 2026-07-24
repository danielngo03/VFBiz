import axe from "axe-core";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Button } from "@/components/ui/button";
import { ConfirmationDialog } from "@/components/ui/confirmation-dialog";

describe("ConfirmationDialog", () => {
  it("keeps confirmation explicit and has no serious accessibility violation", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(
      <ConfirmationDialog
        actionLabel="Xóa phiên"
        description="Phiên đã chọn sẽ bị thu hồi và không thể sử dụng lại."
        onConfirm={onConfirm}
        title="Thu hồi phiên đăng nhập?"
      >
        <Button variant="danger">Thu hồi</Button>
      </ConfirmationDialog>,
    );

    const trigger = screen.getByRole("button", { name: "Thu hồi" });
    trigger.focus();
    await user.click(trigger);
    const dialog = screen.getByRole("alertdialog", {
      name: "Thu hồi phiên đăng nhập?",
    });
    expect(dialog).toBeVisible();

    const results = await axe.run(dialog);
    expect(
      results.violations.filter((violation) =>
        ["critical", "serious"].includes(violation.impact ?? ""),
      ),
    ).toEqual([]);

    await user.keyboard("{Escape}");
    expect(trigger).toHaveFocus();

    await user.click(trigger);
    await user.click(screen.getByRole("button", { name: "Xóa phiên" }));
    expect(onConfirm).toHaveBeenCalledOnce();
    expect(trigger).toHaveFocus();
  });
});
