---
id: delivery-and-authority
title: Delivery, ownership và authority
status: active
owner_role: engineering-lead
scope: root
when_to_read:
  - triage
  - discovery
  - escalation
  - controlled
tags:
  - delivery
  - authority
  - product
revision: 2
review_date: 2026-09-01
supersedes:
  - task-routing
  - roles-authority
  - department-team-topology
  - product-lifecycle
---

# Delivery and authority

Departments are durable ownership boundaries. Agent roles are temporary
execution capabilities and are never legal or approval authorities.

## Delivery modes

| Mode | Trigger | Artifact | Questions | Extra docs |
| --- | --- | --- | ---: | ---: |
| Fast | Local, reversible, low-risk and clear | None | 0 | 0 |
| Bounded | One clear workspace outcome | Work item | 1 blocking round | 3 |
| Controlled | Auth, PII, payment, migration, public contract, AI or production | Work item; ExecPlan when multi-phase | 2 decision rounds | 6 |
| Discovery | Value, owner, data or provider unclear | Decision brief | 2 rounds | 3 |
| Parallel | Disjoint lanes with integration owner | Work items plus ExecPlan | Inherited per lane | 8/lane |

Risk, complexity, uncertainty and scope are independent. Complexity never
reduces a controlled signal.

## Autonomy

1. Act when the decision is approved, owned, reversible and safe.
2. Record a safe assumption when ambiguity is non-material and reversible.
3. Coordinate directly with the owner of a required interface.
4. Escalate with evidence, at most three options and one recommendation when
   outcome, scope, contract, architecture or risk changes.
5. Stop only the affected lane when authority, trustworthy data, rights,
   rollback or safety evidence is missing.

## Human authority

| Role | Accountable decision |
| --- | --- |
| Executive Sponsor | Goals, budget and strategic priority |
| Product Owner | Product value, scope, MVP and acceptance |
| Product Manager | Sequence, dependency and capacity |
| Business Owner | Process and business policy |
| Design Lead | Experience, accessibility and brand acceptance |
| Architect | Cross-system boundaries and accepted ADRs |
| Security/Privacy/Legal/Data owners | Risk and exception acceptance |
| Engineering Lead | Technical accountability |
| Release Owner | Production release, rollback and incident authority |

Agents advise and implement. They never substitute for these decisions.

## Product, delivery và business analysis

| Vai trò | Trách nhiệm chính | Không tự quyết |
| --- | --- | --- |
| Product Owner (PO) | Outcome, value, priority, phạm vi MVP và product acceptance | Kiến trúc, risk exception hoặc production release |
| Product Manager (PM) | Sequencing, dependency, capacity, milestone và báo cáo theo ngoại lệ | Đổi outcome hoặc chấp nhận rủi ro thay PO/Risk Owner |
| Business Analyst (BA) | As-is/to-be flow, terminology, business rule, exception, data meaning, acceptance và traceability | Priority, kiến trúc hoặc risk acceptance |
| Product Analyst | Insight, metric, option và evidence cho product decision | Scope hoặc acceptance thay PO |
| Data Owner | Mục đích sử dụng, classification, access và data-risk decision | Triển khai pipeline hoặc tự promote AI release |
| Data Steward | Metadata, provenance, quality, freshness, retention và lineage evidence | Chấp nhận data/privacy/legal risk thay owner |

BA, Product Analyst và Data Steward là supporting human roles. Chúng không trở
thành runtime agent bắt buộc. Khi cần, orchestrator giao deliverable tương ứng
cho `explorer`, `implementer` hoặc `reviewer-verifier`; human authority vẫn giữ
quyết định được nêu ở bảng trên.

## Department, team, workspace và runtime role

Bốn khái niệm này không thay thế nhau:

- **Department** là ranh giới ownership bền vững, ví dụ Digital Platform hoặc
  AI & Data.
- **Team** sở hữu capability và path cụ thể; team lead chịu technical
  accountability nhưng không tự nhận product/risk authority.
- **Workspace** là boundary code và instruction, ví dụ `backend/api` hoặc
  `backend/ai`; một workspace có thể có nhiều team.
- **Runtime role** là năng lực tạm thời của một agent run: explore, implement,
  review, risk review hoặc integrate. Provider/model không thay đổi authority.

Digital Platform hiện có API Foundation, Customer & Product, Customer
Engagement và Mobility Platform. AI & Data có AI Platform Foundation, AI
Assistant Orchestration, AI Model Platform, AI Knowledge Engineering, AI
Assurance và Data Governance. Phân tách này tạo separation of duties trong
routing mà không tạo thêm agent theo chức danh hoặc buộc task nhỏ phải qua mọi
team.

## Luồng giao việc mặc định

1. PO xác nhận outcome/prioritization khi yêu cầu làm thay đổi sản phẩm.
2. BA làm rõ rule, exception, data meaning và acceptance khi chưa đủ rõ; thay
   đổi kỹ thuật đã rõ không bắt buộc đi qua BA.
3. PM chỉ tham gia khi có dependency, capacity, milestone hoặc nhiều lane.
4. Resolver chọn một owner team theo path/capability và chỉ nạp local context.
5. Một implementer có thể hoàn thành trọn bounded capability. Controlled signal
   mới kích hoạt verifier/risk reviewer và human gate tương ứng.
6. Dependency ngang dùng Coordination Request tới đúng owner; không broadcast
   toàn bộ lịch sử chat hoặc chuyển việc tuần tự qua nhiều cấp.

## Workspace ownership

- Root: product, cross-system architecture, contracts, governance and work
  state.
- API: public contract, authorization, transactions and integrations.
- AI: retrieval, inference policy, evaluation and tool proposals.
- Drupal: CMS, public SSR, editorial workflow and SEO.
- Customer clients: authenticated web/mobile presentation and local state.
- Workforce Portal: workforce workflows constrained by API authority.
- Identity Theme: Keycloak login/email theme and identity experience,
  constrained by Identity Platform authority.
- Infra: environments, delivery, observability and recovery.

## Product artifacts and states

- Small visual/copy/known defects need no work artifact.
- Bounded behavior uses a short work item.
- Multi-story product behavior uses a PRD-lite linked from the work item.
- Cross-system or material controlled scope uses a full PRD and, when
  multi-phase, an ExecPlan.

`code-complete`, `acceptance-complete`, `released` and `outcome-validated` are
distinct. Git records technical and delivery truth; external tools may display
it but do not replace it.
