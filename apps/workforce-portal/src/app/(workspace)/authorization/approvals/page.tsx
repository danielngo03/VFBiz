import {Suspense} from 'react';
import {ResourcePage} from '@/components/layout/resource-page';
import {ApprovalsPanel} from '@/features/authorization/components/approvals-panel';
import {ApprovalsPanelSkeleton} from '@/features/authorization/components/approvals-panel-skeleton';

export default function ApprovalsPage() {
  return (
    <ResourcePage eyebrow="Maker-checker" title="Yêu cầu phê duyệt" description="Các thay đổi đặc quyền phải có người đề xuất và người phê duyệt độc lập. Màn hình này chỉ hiển thị hàng đợi, chưa thực hiện mutation.">
      <Suspense fallback={<ApprovalsPanelSkeleton />}><ApprovalsPanel /></Suspense>
    </ResourcePage>
  );
}
