# Agent operating model cho Customer Mobile

## Nguyên tắc

Agents không phải phòng ban và không tự tạo authority. Department/team/human role
trong `.agents/organization.json` sở hữu quyết định; agent role chỉ thực thi một
lane có objective, allowed paths, stop condition và evidence rõ.

Canonical communication là work item, ExecPlan, ADR, review finding và CI result.
Chat giữa agents dùng để chuyển evidence/ngữ cảnh ngắn; không thay product scope,
architecture decision, security/privacy acceptance hoặc release approval.

## Các agent tham gia một Customer change

| Agent role | Trách nhiệm | Không được làm |
| --- | --- | --- |
| Orchestrator | phân loại, claim/lease, định tuyến owner/reviewer, checkpoint | tự chấp nhận risk/release |
| Explorer | đọc repo/Expo/contract, trả evidence và options | sửa runtime |
| Implementer | một writer trong allowed paths, chạy checks | mở rộng scope hoặc sửa finding ngoài lane |
| Reviewer-verifier | kiểm acceptance/regression/maintainability độc lập | silently fix hoặc approve release |
| Risk-reviewer | security/privacy/dependency/release findings | chấp nhận exception/risk |
| Integrator | hợp nhất disjoint lanes và cross-lane checks | thay Architect/Product quyết định |

Một task mặc định dùng một orchestrator, một implementer và reviewer cần thiết.
Tối đa ba direct worker khi paths thực sự disjoint; Customer config, auth callback,
native dependencies, design-token output và lockfile là exclusive resources.

## Department và human routing

| Chủ đề | Team phối hợp | Human authority |
| --- | --- | --- |
| Customer outcome/journey | Product Management + Mobile Experience | product-owner/product-manager |
| Expo/app architecture | Mobile Experience + Architecture & Integration | engineering-lead + architect |
| PKCE/realm/callback | Identity Experience + Mobile Experience | identity-platform-owner + security-owner |
| Public resource contract | API Foundation + Architecture & Integration | engineering-lead + architect |
| PII/cache/offline/telemetry | Mobile Experience + Architecture & Risk | privacy-owner + security-owner + data-owner |
| Visual/accessibility/brand | Mobile Experience | design-lead + legal-owner khi có asset |
| EAS/build/OTA/store | Mobile Experience + Reliability Engineering | release-owner + security-owner |
| AI entrypoint | Customer Engagement + API authority | product-owner + security/privacy owners |

## Communication protocol

1. Orchestrator tạo/resume work item và context key; scope/allowed paths/exclusive
   resources được ghi trước khi writer bắt đầu.
2. Explorer trả source/evidence/options; human/ADR quyết định phần khó đảo ngược.
3. Implementer checkpoint revision, changed paths, observed checks, blockers và
   một exact next action.
4. Reviewer/risk reviewer trả finding có severity, path, reproduction/evidence;
   writer không tự đóng finding nếu chưa có check mới.
5. Sau tối đa hai fix/review cycles, unresolved controlled finding chuyển human
   owner. CI là enforcement authority cuối, Release Owner mới phát hành.

Không tạo “agents tự nói chuyện vô hạn”, phòng ban giả, generic shared agent hoặc
role `expo-agent/ios-agent/android-agent`. Specialization nằm trong assignment và
skill selection, còn accountability vẫn thuộc human role.
