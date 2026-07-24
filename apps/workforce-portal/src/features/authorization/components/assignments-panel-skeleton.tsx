import {ResourceTableSkeleton} from '@/components/feedback/resource-table-skeleton';

export function AssignmentsPanelSkeleton() {
  return (
    <ResourceTableSkeleton columns={6} label="Đang tải danh sách phân công quyền" />
  );
}
