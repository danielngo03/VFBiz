---
report_id: VFBIZ-WEEK-01
title: Báo cáo tuần 1 — Xây dựng nền tảng VFBiz
period_start: 2026-07-20
period_end: 2026-07-24
audience: mentor
owner_role: product-owner
status: draft
---

# Báo cáo tuần 1 — Xây dựng nền tảng VFBiz

**Thời gian:** 20/07/2026 – 24/07/2026

**Mục tiêu tuần:** Xây dựng nền tảng kỹ thuật và cách vận hành dự án trước khi
phát triển Customer Chatbot và Lập kế hoạch hành trình EV.

## 1. Kết quả chính

Trong tuần 1, dự án đã hình thành được nền tảng chung cho hệ sinh thái VFBiz:

- Tổ chức repository theo các khu vực độc lập: Backend API, AI Platform,
  Customer Portal, Workforce Portal, Drupal, Mobile và hạ tầng.
- Xây dựng Backend API bằng NestJS theo kiến trúc module, có PostgreSQL 17,
  PostGIS, Redis, OpenAPI và tài liệu API bằng Scalar.
- Xây dựng nền tảng Account, Customer và Product gồm đăng nhập qua Keycloak,
  hồ sơ khách hàng, consent, yêu cầu xuất/xóa dữ liệu, session, Customer Garage,
  danh mục xe, nguồn dữ liệu và quy trình phát hành dữ liệu.
- Tách hai nhóm định danh: khách hàng và nhân sự. Keycloak quản lý đăng nhập,
  MFA và credential; PostgreSQL lưu dữ liệu nghiệp vụ/audit; Redis giữ
  session/token ngắn hạn.
- Xây dựng Customer Portal và Workforce Portal bằng Next.js theo cấu trúc
  feature-first; bổ sung BFF, token vault phía server và các kiểm soát bảo mật
  phiên đăng nhập.
- Xây dựng nền tảng phân quyền động cho Workforce theo capability, role, phạm vi
  tổ chức và cơ chế người tạo khác người phê duyệt.
- Xây dựng Identity Theme dùng chung design token cho trang đăng nhập Customer
  và Workforce, hỗ trợ tiếng Việt/tiếng Anh.
- Chuẩn bị nền tảng FastAPI cho AI, các contract quản trị dataset, evaluation và
  AI release; chưa triển khai Customer Chatbot runtime trong tuần này.
- Hoàn thiện bộ tài liệu tổng quan về sản phẩm, kiến trúc, bảo mật, Chatbot và
  Lập kế hoạch hành trình EV để làm cơ sở cho các giai đoạn tiếp theo.

## 2. Công việc theo ngày

| Ngày  | Công việc trọng tâm                         | Kết quả                                                                                                                         |
| ----- | ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| 20/07 | Khởi tạo cấu trúc dự án và quy tắc vận hành | Tách các workspace, thiết lập Drupal foundation, agent routing, context resolver và contract quản trị AI/data.                  |
| 21/07 | Chuẩn hóa governance                        | Bổ sung kiểm soát ranh giới workspace, tài liệu, security work item và quy tắc làm việc độc lập với provider.                   |
| 22/07 | Xây dựng lại Backend                        | Khởi tạo NestJS và FastAPI theo cấu trúc module; bổ sung config, OIDC, persistence, health check và PostgreSQL foundation.      |
| 23/07 | Hoàn thiện nền tảng Account/Product         | Bổ sung authorization, customer session, account, vehicle data, API docs, local development và phân chia ownership API/AI/Data. |
| 24/07 | Chuẩn hóa Portal và Identity                | Refactor hai Next.js Portal, tách session core, hoàn thiện Keycloak Identity Theme và bộ báo cáo kiến trúc tổng quan.           |

## 3. Cách tổ chức và phối hợp agent

- Một agent chính giữ vai trò điều phối, chia công việc theo workspace và
  đường dẫn rõ ràng.
- Các agent triển khai, kiểm thử, review và đánh giá rủi ro có phạm vi riêng;
  agent thực thi không tự phê duyệt kết quả của mình.
- Tối đa ba luồng viết code song song; không cho hai agent cùng sửa một khu vực
  hoặc tài nguyên dùng chung.
- Mỗi công việc có work item, owner, dependency, điều kiện hoàn thành và bằng
  chứng kiểm thử trong Git.
- Context được cấp theo đúng nhiệm vụ; agent không đọc toàn bộ tài liệu, giúp
  giảm token, tránh hiểu sai và hạn chế lặp vô ích.
- Retry và review đều có giới hạn; vấn đề không giải quyết được phải chuyển về
  người có thẩm quyền thay vì để agent tự suy đoán.

## 4. Kiểm tra chất lượng

- Đã thiết lập các gate cho lint, typecheck, unit test, integration test,
  OpenAPI contract, migration, build và governance.
- API, Portal, agent routing và tài liệu được kiểm tra bằng script dùng chung,
  không phụ thuộc vào một model/provider cụ thể.
- Các luồng nhạy cảm áp dụng nguyên tắc deny-by-default, không lưu password,
  OTP hoặc token trong trình duyệt và không dùng dữ liệu production trong môi
  trường phát triển.

## 5. Phần đang tiếp tục hoàn thiện

- Một số hạng mục hiện ở trạng thái review hoặc chờ browser E2E, chưa được coi
  là production-ready.
- Customer Portal cần hoàn tất đầy đủ các hành trình profile, security,
  privacy và Garage trên giao diện.
- Workforce Portal cần hoàn tất quản trị role, assignment, approval và audit.
- Chatbot, RAG runtime và Lập kế hoạch hành trình EV chưa được triển khai trong
  tuần 1; mới hoàn thành kiến trúc, contract và kế hoạch phát triển.

## 6. MVP tuần 2

**Thời gian dự kiến:** 27/07/2026 – 31/07/2026

**Mục tiêu:** Hoàn tất vòng nghiệm thu nền tảng Customer/Workforce và tạo một
luồng Customer Chatbot an toàn chạy xuyên suốt trên staging/local.

### Phạm vi ưu tiên

1. Hoàn tất Customer Portal: profile, security, session, consent, yêu cầu dữ
   liệu và Customer Garage.
2. Hoàn tất Workforce Portal: role, capability, assignment, approval và audit.
3. Hoàn tất browser E2E cho Keycloak, hai Portal và các luồng đăng nhập/MFA/
   logout.
4. Khóa contract Account, Customer và Vehicle; bổ sung dữ liệu mẫu có nguồn,
   version và trạng thái phê duyệt rõ ràng.
5. Triển khai Chatbot MVP:
   - tạo và duy trì phiên hội thoại;
   - trả lời từ nguồn tri thức đã được phê duyệt;
   - câu trả lời factual có citation;
   - từ chối khi thiếu bằng chứng;
   - chuyển nhân viên CSKH khi cần;
   - chưa có tool gây thay đổi dữ liệu.

### Điều kiện hoàn thành

- Các luồng Customer và Workforce chính chạy E2E.
- Không có lỗi bảo mật mức Critical/High chưa xử lý.
- Chatbot không tự tạo giá, chính sách hoặc thông số xe.
- Mọi câu trả lời factual của Chatbot có citation hợp lệ hoặc từ chối.
- Có demo ngắn và evidence liên kết từ work item.

**Ngoài MVP tuần 2:** EV Planner, thanh toán/đặt cọc, mobile hoàn chỉnh,
fine-tuning và production release.
