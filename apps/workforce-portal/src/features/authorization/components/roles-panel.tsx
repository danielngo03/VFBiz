import {ResourceState, StatusBadge} from '@/components/layout/resource-page';
import {formatWorkforceDateTime} from '@/platform/api/workforce-resources';
import {loadCurrentWorkforceData} from '@/platform/session/current-workforce-context';

export async function RolesPanel() {
  const state = await loadCurrentWorkforceData(
    ['authorization.role.read'],
    (client, request) => client.listRoles(request),
  );
  if (state.status !== 'ready') {
    return (
      <ResourceState
        kind={state.status}
        correlationId={state.status === 'unavailable' ? state.correlationId : undefined}
      />
    );
  }
  if (state.data.length === 0) return <ResourceState kind="empty" />;
  return (
    <div className="table-scroll">
      <table>
        <caption>Danh sách role trong phạm vi được cấp</caption>
        <thead><tr><th scope="col">Role</th><th scope="col">Trạng thái</th><th scope="col">Loại</th><th scope="col">Capability</th><th scope="col">Phiên bản</th><th scope="col">Cập nhật</th></tr></thead>
        <tbody>
          {state.data.map((role) => (
            <tr key={role.id}>
              <th scope="row"><strong>{role.displayName}</strong><code className="secondary-code">{role.key}</code></th>
              <td><StatusBadge tone={role.status === 'active' ? 'positive' : 'neutral'}>{role.status === 'active' ? 'Đang hoạt động' : 'Đã vô hiệu'}</StatusBadge></td>
              <td>{role.system ? 'Hệ thống' : 'Tùy chỉnh'}</td>
              <td>{role.capabilityKeys.length}</td><td>v{role.version}</td>
              <td>{formatWorkforceDateTime(role.updatedAt)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
