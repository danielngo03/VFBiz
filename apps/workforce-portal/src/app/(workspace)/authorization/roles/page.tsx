import {Suspense} from 'react';
import {ResourcePage} from '@/components/layout/resource-page';
import {RolesPanel} from '@/features/authorization/components/roles-panel';
import {RolesPanelSkeleton} from '@/features/authorization/components/roles-panel-skeleton';

export default function RolesPage() {
  return (
    <ResourcePage eyebrow="Authorization" title="Role và capability" description="Các role động được lưu tại Authorization Platform. Capability key do code quản lý và không thể tạo tùy ý từ giao diện.">
      <Suspense fallback={<RolesPanelSkeleton />}><RolesPanel /></Suspense>
    </ResourcePage>
  );
}
