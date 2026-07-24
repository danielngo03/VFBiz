import {Suspense} from 'react';
import {ResourcePage} from '@/components/layout/resource-page';
import {AuditPanel} from '@/features/audit/components/audit-panel';
import {AuditPanelSkeleton} from '@/features/audit/components/audit-panel-skeleton';

export default function AuditPage() {
  return (
    <ResourcePage eyebrow="Audit" title="Nhật ký kiểm toán" description="Timeline read-only từ API. Portal không lưu bản sao, không suy diễn sự kiện và không hiển thị token hoặc payload nhạy cảm.">
      <Suspense fallback={<AuditPanelSkeleton />}><AuditPanel /></Suspense>
    </ResourcePage>
  );
}
