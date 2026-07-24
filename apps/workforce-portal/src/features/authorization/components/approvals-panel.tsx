import {ResourceState, StatusBadge} from '@/components/layout/resource-page';
import {formatWorkforceDateTime} from '@/platform/api/workforce-resources';
import {loadCurrentWorkforceData} from '@/platform/session/current-workforce-context';

export async function ApprovalsPanel() {
  const state = await loadCurrentWorkforceData(
    ['authorization.approval.read'],
    (client, request) => client.listChangeRequests(request),
  );
  if (state.status !== 'ready') {
    return <ResourceState kind={state.status} correlationId={state.status === 'unavailable' ? state.correlationId : undefined} />;
  }
  if (state.data.length === 0) return <ResourceState kind="empty" />;
  return (
    <div className="table-scroll">
      <table>
        <caption>Hàng đợi thay đổi authorization</caption>
        <thead><tr><th scope="col">Yêu cầu</th><th scope="col">Đối tượng</th><th scope="col">Người đề xuất</th><th scope="col">Risk tier</th><th scope="col">Hết hạn</th><th scope="col">Trạng thái</th></tr></thead>
        <tbody>
          {state.data.map((request) => (
            <tr key={request.id}>
              <th scope="row"><strong>{request.requestType}</strong><span className="table-note">{request.reason}</span></th>
              <td>{request.targetType}<code className="secondary-code">{request.targetRef}</code></td>
              <td><code>{request.requesterRef}</code></td><td>{request.riskTier}</td>
              <td>{formatWorkforceDateTime(request.expiresAt)}</td>
              <td><StatusBadge tone={request.status === 'pending' ? 'warning' : request.status === 'approved' ? 'positive' : 'neutral'}>{{pending: 'Chờ duyệt', approved: 'Đã duyệt', rejected: 'Đã từ chối'}[request.status]}</StatusBadge></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
