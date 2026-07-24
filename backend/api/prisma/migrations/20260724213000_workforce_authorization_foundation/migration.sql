CREATE TYPE "workforce_capability_risk_tier" AS ENUM ('standard', 'sensitive', 'privileged');
CREATE TYPE "workforce_role_status" AS ENUM ('active', 'disabled');
CREATE TYPE "workforce_assignment_status" AS ENUM ('active', 'revoked');
CREATE TYPE "workforce_scope_type" AS ENUM ('global', 'market', 'showroom', 'department');
CREATE TYPE "authorization_change_request_status" AS ENUM ('pending', 'approved', 'rejected');

CREATE TABLE "workforce_capability_definition" (
  "key" VARCHAR(120) PRIMARY KEY,
  "resource" VARCHAR(100) NOT NULL,
  "action" VARCHAR(40) NOT NULL,
  "riskTier" "workforce_capability_risk_tier" NOT NULL,
  "displayName" VARCHAR(160) NOT NULL,
  "deprecated" BOOLEAN NOT NULL DEFAULT false,
  "catalogVersion" INTEGER NOT NULL,
  "createdAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMPTZ(6) NOT NULL,
  CONSTRAINT "workforce_capability_key_format"
    CHECK ("key" ~ '^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*){2,3}$')
);

CREATE TABLE "workforce_role" (
  "id" UUID PRIMARY KEY,
  "key" VARCHAR(80) NOT NULL UNIQUE,
  "displayName" VARCHAR(160) NOT NULL,
  "description" VARCHAR(500),
  "status" "workforce_role_status" NOT NULL DEFAULT 'active',
  "system" BOOLEAN NOT NULL DEFAULT false,
  "version" INTEGER NOT NULL DEFAULT 1,
  "createdByRef" VARCHAR(160) NOT NULL,
  "updatedByRef" VARCHAR(160) NOT NULL,
  "createdAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMPTZ(6) NOT NULL,
  CONSTRAINT "workforce_role_key_format"
    CHECK ("key" ~ '^[a-z][a-z0-9-]{0,79}$'),
  CONSTRAINT "workforce_role_positive_version" CHECK ("version" > 0)
);

CREATE TABLE "workforce_role_capability" (
  "roleId" UUID NOT NULL,
  "capabilityKey" VARCHAR(120) NOT NULL,
  "grantedAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "grantedByRef" VARCHAR(160) NOT NULL,
  PRIMARY KEY ("roleId", "capabilityKey"),
  CONSTRAINT "workforce_role_capability_roleId_fkey"
    FOREIGN KEY ("roleId") REFERENCES "workforce_role"("id") ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "workforce_role_capability_capabilityKey_fkey"
    FOREIGN KEY ("capabilityKey") REFERENCES "workforce_capability_definition"("key") ON DELETE RESTRICT ON UPDATE CASCADE
);

CREATE TABLE "workforce_organization_unit_projection" (
  "id" UUID PRIMARY KEY,
  "externalRef" VARCHAR(160) NOT NULL UNIQUE,
  "type" "workforce_scope_type" NOT NULL,
  "displayName" VARCHAR(160) NOT NULL,
  "status" VARCHAR(40) NOT NULL DEFAULT 'active',
  "source" VARCHAR(80) NOT NULL,
  "revision" VARCHAR(160) NOT NULL,
  "observedAt" TIMESTAMPTZ(6) NOT NULL,
  "createdAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMPTZ(6) NOT NULL
);

CREATE TABLE "workforce_role_assignment" (
  "id" UUID PRIMARY KEY,
  "identitySubjectId" UUID NOT NULL,
  "roleId" UUID NOT NULL,
  "status" "workforce_assignment_status" NOT NULL DEFAULT 'active',
  "effectiveAt" TIMESTAMPTZ(6) NOT NULL,
  "expiresAt" TIMESTAMPTZ(6),
  "reason" VARCHAR(500) NOT NULL,
  "version" INTEGER NOT NULL DEFAULT 1,
  "createdByRef" VARCHAR(160) NOT NULL,
  "approvedByRef" VARCHAR(160),
  "revokedAt" TIMESTAMPTZ(6),
  "revokedByRef" VARCHAR(160),
  "createdAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMPTZ(6) NOT NULL,
  CONSTRAINT "workforce_role_assignment_identitySubjectId_fkey"
    FOREIGN KEY ("identitySubjectId") REFERENCES "identity_subject"("id") ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "workforce_role_assignment_roleId_fkey"
    FOREIGN KEY ("roleId") REFERENCES "workforce_role"("id") ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "workforce_assignment_valid_period"
    CHECK ("expiresAt" IS NULL OR "expiresAt" > "effectiveAt"),
  CONSTRAINT "workforce_assignment_revocation_consistency"
    CHECK (
      ("status" = 'active' AND "revokedAt" IS NULL AND "revokedByRef" IS NULL)
      OR
      ("status" = 'revoked' AND "revokedAt" IS NOT NULL AND "revokedByRef" IS NOT NULL)
    ),
  CONSTRAINT "workforce_assignment_positive_version" CHECK ("version" > 0)
);

CREATE TABLE "workforce_role_assignment_scope" (
  "assignmentId" UUID NOT NULL,
  "scopeType" "workforce_scope_type" NOT NULL,
  "scopeRef" VARCHAR(160) NOT NULL,
  "organizationUnitId" UUID,
  PRIMARY KEY ("assignmentId", "scopeType", "scopeRef"),
  CONSTRAINT "workforce_role_assignment_scope_assignmentId_fkey"
    FOREIGN KEY ("assignmentId") REFERENCES "workforce_role_assignment"("id") ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "workforce_role_assignment_scope_organizationUnitId_fkey"
    FOREIGN KEY ("organizationUnitId") REFERENCES "workforce_organization_unit_projection"("id") ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "workforce_assignment_global_scope"
    CHECK (
      ("scopeType" = 'global' AND "scopeRef" = 'global' AND "organizationUnitId" IS NULL)
      OR
      ("scopeType" <> 'global' AND "scopeRef" <> 'global' AND "organizationUnitId" IS NOT NULL)
    )
);

CREATE TABLE "authorization_change_request" (
  "id" UUID PRIMARY KEY,
  "requestType" VARCHAR(80) NOT NULL,
  "status" "authorization_change_request_status" NOT NULL DEFAULT 'pending',
  "riskTier" "workforce_capability_risk_tier" NOT NULL,
  "requesterRef" VARCHAR(160) NOT NULL,
  "targetType" VARCHAR(80) NOT NULL,
  "targetRef" VARCHAR(160) NOT NULL,
  "reason" VARCHAR(500) NOT NULL,
  "payload" JSONB NOT NULL,
  "correlationId" UUID NOT NULL,
  "expiresAt" TIMESTAMPTZ(6) NOT NULL,
  "decidedAt" TIMESTAMPTZ(6),
  "createdAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMPTZ(6) NOT NULL,
  CONSTRAINT "authorization_change_request_expiry"
    CHECK ("expiresAt" > "createdAt"),
  CONSTRAINT "authorization_change_request_decision_consistency"
    CHECK (
      ("status" = 'pending' AND "decidedAt" IS NULL)
      OR
      ("status" <> 'pending' AND "decidedAt" IS NOT NULL)
    )
);

CREATE TABLE "authorization_change_approval" (
  "id" UUID PRIMARY KEY,
  "changeRequestId" UUID NOT NULL UNIQUE,
  "decision" VARCHAR(40) NOT NULL,
  "approverRef" VARCHAR(160) NOT NULL,
  "evidenceRef" VARCHAR(512) NOT NULL,
  "reason" VARCHAR(500),
  "decidedAt" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "authorization_change_approval_changeRequestId_fkey"
    FOREIGN KEY ("changeRequestId") REFERENCES "authorization_change_request"("id") ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT "authorization_change_approval_decision"
    CHECK ("decision" IN ('approved', 'rejected'))
);

CREATE TABLE "workforce_entitlement_revision" (
  "identitySubjectId" UUID PRIMARY KEY,
  "revision" BIGINT NOT NULL DEFAULT 1,
  "updatedAt" TIMESTAMPTZ(6) NOT NULL,
  CONSTRAINT "workforce_entitlement_revision_identitySubjectId_fkey"
    FOREIGN KEY ("identitySubjectId") REFERENCES "identity_subject"("id") ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "workforce_entitlement_positive_revision" CHECK ("revision" > 0)
);

CREATE INDEX "workforce_capability_definition_resource_action_idx"
  ON "workforce_capability_definition"("resource", "action");
CREATE INDEX "workforce_capability_definition_riskTier_deprecated_idx"
  ON "workforce_capability_definition"("riskTier", "deprecated");
CREATE INDEX "workforce_role_status_displayName_idx"
  ON "workforce_role"("status", "displayName");
CREATE INDEX "workforce_role_capability_capabilityKey_idx"
  ON "workforce_role_capability"("capabilityKey");
CREATE INDEX "workforce_organization_unit_projection_type_status_idx"
  ON "workforce_organization_unit_projection"("type", "status");
CREATE INDEX "workforce_role_assignment_identitySubjectId_status_effectiv_idx"
  ON "workforce_role_assignment"("identitySubjectId", "status", "effectiveAt", "expiresAt");
CREATE INDEX "workforce_role_assignment_roleId_status_idx"
  ON "workforce_role_assignment"("roleId", "status");
CREATE INDEX "workforce_role_assignment_scope_scopeType_scopeRef_idx"
  ON "workforce_role_assignment_scope"("scopeType", "scopeRef");
CREATE INDEX "workforce_role_assignment_scope_organizationUnitId_idx"
  ON "workforce_role_assignment_scope"("organizationUnitId");
CREATE INDEX "authorization_change_request_status_expiresAt_createdAt_idx"
  ON "authorization_change_request"("status", "expiresAt", "createdAt");
CREATE INDEX "authorization_change_request_targetType_targetRef_idx"
  ON "authorization_change_request"("targetType", "targetRef");
CREATE INDEX "authorization_change_approval_approverRef_decidedAt_idx"
  ON "authorization_change_approval"("approverRef", "decidedAt");

INSERT INTO "workforce_capability_definition"
  ("key", "resource", "action", "riskTier", "displayName", "catalogVersion", "updatedAt")
VALUES
  ('authorization.role.read', 'authorization.role', 'read', 'sensitive', 'Xem vai trò', 1, CURRENT_TIMESTAMP),
  ('authorization.role.create', 'authorization.role', 'create', 'privileged', 'Tạo vai trò', 1, CURRENT_TIMESTAMP),
  ('authorization.role.update', 'authorization.role', 'update', 'privileged', 'Cập nhật vai trò', 1, CURRENT_TIMESTAMP),
  ('authorization.role.disable', 'authorization.role', 'disable', 'privileged', 'Vô hiệu hóa vai trò', 1, CURRENT_TIMESTAMP),
  ('authorization.assignment.read', 'authorization.assignment', 'read', 'sensitive', 'Xem phân quyền', 1, CURRENT_TIMESTAMP),
  ('authorization.assignment.create', 'authorization.assignment', 'create', 'privileged', 'Cấp vai trò', 1, CURRENT_TIMESTAMP),
  ('authorization.assignment.revoke', 'authorization.assignment', 'revoke', 'privileged', 'Thu hồi vai trò', 1, CURRENT_TIMESTAMP),
  ('authorization.approval.read', 'authorization.approval', 'read', 'sensitive', 'Xem yêu cầu phê duyệt', 1, CURRENT_TIMESTAMP),
  ('authorization.approval.approve', 'authorization.approval', 'approve', 'privileged', 'Phê duyệt thay đổi quyền', 1, CURRENT_TIMESTAMP),
  ('authorization.approval.reject', 'authorization.approval', 'reject', 'privileged', 'Từ chối thay đổi quyền', 1, CURRENT_TIMESTAMP),
  ('customer-support.case.read', 'customer-support.case', 'read', 'sensitive', 'Xem hồ sơ hỗ trợ', 1, CURRENT_TIMESTAMP),
  ('customer-support.case.update', 'customer-support.case', 'update', 'sensitive', 'Cập nhật hồ sơ hỗ trợ', 1, CURRENT_TIMESTAMP),
  ('customer-support.case.close', 'customer-support.case', 'close', 'sensitive', 'Đóng hồ sơ hỗ trợ', 1, CURRENT_TIMESTAMP),
  ('vehicle-catalog.release.read', 'vehicle-catalog.release', 'read', 'standard', 'Xem bản phát hành dữ liệu xe', 1, CURRENT_TIMESTAMP),
  ('vehicle-catalog.release.submit', 'vehicle-catalog.release', 'submit', 'sensitive', 'Gửi duyệt dữ liệu xe', 1, CURRENT_TIMESTAMP),
  ('vehicle-catalog.release.approve', 'vehicle-catalog.release', 'approve', 'privileged', 'Duyệt dữ liệu xe', 1, CURRENT_TIMESTAMP),
  ('vehicle-catalog.release.activate', 'vehicle-catalog.release', 'activate', 'privileged', 'Kích hoạt dữ liệu xe', 1, CURRENT_TIMESTAMP),
  ('vehicle-catalog.release.rollback', 'vehicle-catalog.release', 'rollback', 'privileged', 'Rollback dữ liệu xe', 1, CURRENT_TIMESTAMP),
  ('commercial-data.release.approve', 'commercial-data.release', 'approve', 'privileged', 'Duyệt dữ liệu thương mại', 1, CURRENT_TIMESTAMP),
  ('commercial-data.release.activate', 'commercial-data.release', 'activate', 'privileged', 'Kích hoạt dữ liệu thương mại', 1, CURRENT_TIMESTAMP),
  ('commercial-data.release.rollback', 'commercial-data.release', 'rollback', 'privileged', 'Rollback dữ liệu thương mại', 1, CURRENT_TIMESTAMP),
  ('audit.event.read', 'audit.event', 'read', 'sensitive', 'Xem nhật ký kiểm toán', 1, CURRENT_TIMESTAMP),
  ('audit.event.export', 'audit.event', 'export', 'privileged', 'Xuất nhật ký kiểm toán', 1, CURRENT_TIMESTAMP);

INSERT INTO "workforce_role"
  ("id", "key", "displayName", "description", "system", "createdByRef", "updatedByRef", "updatedAt")
VALUES
  (gen_random_uuid(), 'authorization-reader', 'Người xem phân quyền', 'System role for authorization read access.', true, 'migration:VFBIZ-0056', 'migration:VFBIZ-0056', CURRENT_TIMESTAMP),
  (gen_random_uuid(), 'vehicle-data-reviewer', 'Người duyệt dữ liệu xe', 'Compatibility role for the existing vehicle release workflow.', true, 'migration:VFBIZ-0056', 'migration:VFBIZ-0056', CURRENT_TIMESTAMP),
  (gen_random_uuid(), 'vehicle-data-operator', 'Người vận hành dữ liệu xe', 'Compatibility role for activate and rollback operations.', true, 'migration:VFBIZ-0056', 'migration:VFBIZ-0056', CURRENT_TIMESTAMP),
  (gen_random_uuid(), 'commercial-data-reviewer', 'Người duyệt dữ liệu thương mại', 'Compatibility role for the existing commercial release workflow.', true, 'migration:VFBIZ-0056', 'migration:VFBIZ-0056', CURRENT_TIMESTAMP),
  (gen_random_uuid(), 'commercial-data-operator', 'Người vận hành dữ liệu thương mại', 'Compatibility role for activate and rollback operations.', true, 'migration:VFBIZ-0056', 'migration:VFBIZ-0056', CURRENT_TIMESTAMP);

INSERT INTO "workforce_role_capability" ("roleId", "capabilityKey", "grantedByRef")
SELECT role."id", capability."key", 'migration:VFBIZ-0056'
FROM "workforce_role" role
JOIN "workforce_capability_definition" capability
  ON (
    (role."key" = 'authorization-reader' AND capability."key" IN (
      'authorization.role.read',
      'authorization.assignment.read',
      'authorization.approval.read'
    ))
    OR (role."key" = 'vehicle-data-reviewer' AND capability."key" = 'vehicle-catalog.release.approve')
    OR (role."key" = 'vehicle-data-operator' AND capability."key" IN (
      'vehicle-catalog.release.activate',
      'vehicle-catalog.release.rollback'
    ))
    OR (role."key" = 'commercial-data-reviewer' AND capability."key" = 'commercial-data.release.approve')
    OR (role."key" = 'commercial-data-operator' AND capability."key" IN (
      'commercial-data.release.activate',
      'commercial-data.release.rollback'
    ))
  );
