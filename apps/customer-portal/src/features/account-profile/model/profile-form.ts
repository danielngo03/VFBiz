import { z } from "zod";

export const profileFormSchema = z.object({
  displayName: z
    .string()
    .trim()
    .max(120, "Tên hiển thị không được vượt quá 120 ký tự."),
  email: z.boolean(),
  expectedEtag: z
    .string()
    .regex(/^(?:W\/)?"profile-\d+"$/u, "Phiên bản hồ sơ không hợp lệ."),
  locale: z.enum(["vi", "en"], {
    error: "Vui lòng chọn ngôn ngữ hợp lệ.",
  }),
  push: z.boolean(),
  sms: z.boolean(),
  timezone: z.enum([
    "Asia/Ho_Chi_Minh",
    "Asia/Bangkok",
    "Asia/Singapore",
    "UTC",
  ]),
});
