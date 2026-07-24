import {Suspense} from 'react';
import {ResourcePage} from '@/components/layout/resource-page';
import {AssignmentsPanel} from '@/features/authorization/components/assignments-panel';
import {AssignmentsPanelSkeleton} from '@/features/authorization/components/assignments-panel-skeleton';

export default function AssignmentsPage() {
  return (
    <ResourcePage eyebrow="Authorization" title="Phân công quyền" description="Mỗi assignment gắn một role với một identity và phạm vi tổ chức cụ thể. Dữ liệu được tải trực tiếp từ Workforce API.">
      <Suspense fallback={<AssignmentsPanelSkeleton />}><AssignmentsPanel /></Suspense>
    </ResourcePage>
  );
}
