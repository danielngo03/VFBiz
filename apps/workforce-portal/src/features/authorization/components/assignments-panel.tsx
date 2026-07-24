import {ResourceState, StatusBadge} from '@/components/layout/resource-page';
import {formatAuthorizationScope, formatWorkforceDateTime} from '@/platform/api/workforce-resources';
import {loadCurrentWorkforceData} from '@/platform/session/current-workforce-context';

export async function AssignmentsPanel() {
  const state = await loadCurrentWorkforceData(
    ['authorization.assignment.read'],
    (client, request) => client.listAssignments(request),
  );
  if (state.status !== 'ready') {
    return <ResourceState kind={state.status} correlationId={state.status === 'unavailable' ? state.correlationId : undefined} />;
  }
  if (state.data.length === 0) return <ResourceState kind="empty" />;
  return (
    <div className="table-scroll">
      <table>
        <caption>Danh sách assignment trong phạm vi được cấp</caption>
        <thead><tr><th scope="col">Identity</th><th scope="col">Role</th><th scope="col">Phạm vi</th><th scope="col">Hiệu lực</th><th scope="col">Hết hạn</th><th scope="col">Trạng thái</th></tr></thead>
        <tbody>
          {state.data.map((assignment) => (
            <tr key={assignment.id}>
              <th scope="row"><code>{assignment.identitySubjectId}</code></th>
              <td><code>{assignment.roleKey}</code></td>
              <td><ul className="compact-list">{assignment.scopes.map((scope) => <li key={`${scope.type}:${scope.ref}`}>{formatAuthorizationScope(scope)}</li>)}</ul></td>
              <td>{formatWorkforceDateTime(assignment.effectiveAt)}</td>
              <td>{assignment.expiresAt ? formatWorkforceDateTime(assignment.expiresAt) : 'Không đặt'}</td>
              <td><StatusBadge tone={assignment.status === 'active' ? 'positive' : 'neutral'}>{assignment.status === 'active' ? 'Đang hiệu lực' : 'Đã thu hồi'}</StatusBadge></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
