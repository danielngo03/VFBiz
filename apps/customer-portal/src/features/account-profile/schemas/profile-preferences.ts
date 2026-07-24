import { z } from "zod";

export const profilePreferencesSchema = z.object({
  displayName: z
    .string()
    .trim()
    .min(1, "Vui lòng nhập tên hiển thị.")
    .max(120, "Tên hiển thị không được vượt quá 120 ký tự."),
  locale: z.enum(["vi-VN", "en-US"]),
  timezone: z.string().trim().min(1, "Vui lòng chọn múi giờ."),
});

export type ProfilePreferencesInput = z.infer<
  typeof profilePreferencesSchema
>;
