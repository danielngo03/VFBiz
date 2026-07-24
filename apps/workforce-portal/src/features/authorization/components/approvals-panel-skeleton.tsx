import {ResourceTableSkeleton} from '@/components/feedback/resource-table-skeleton';

export function ApprovalsPanelSkeleton() {
  return (
    <ResourceTableSkeleton columns={6} label="Đang tải hàng đợi phê duyệt" />
  );
}
