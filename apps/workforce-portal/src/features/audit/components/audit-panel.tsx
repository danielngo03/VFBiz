import {ResourceState, StatusBadge} from '@/components/layout/resource-page';
import {formatWorkforceDateTime} from '@/platform/api/workforce-resources';
import {loadCurrentWorkforceData} from '@/platform/session/current-workforce-context';

export async function AuditPanel() {
  const state = await loadCurrentWorkforceData(
    ['audit.event.read'],
    (client, request) => client.listAuditEvents(request),
  );
  if (state.status !== 'ready') {
    return <ResourceState kind={state.status} correlationId={state.status === 'unavailable' ? state.correlationId : undefined} />;
  }
  if (state.data.length === 0) return <ResourceState kind="empty" />;
  return (
    <div className="table-scroll">
      <table>
        <caption>Các sự kiện authorization gần đây</caption>
        <thead><tr><th scope="col">Thời điểm</th><th scope="col">Hành động</th><th scope="col">Tài nguyên</th><th scope="col">Actor</th><th scope="col">Kết quả</th><th scope="col">Correlation ID</th></tr></thead>
        <tbody>{state.data.map((event) => (
          <tr key={event.id}>
            <th scope="row">{formatWorkforceDateTime(event.occurredAt)}</th><td><code>{event.action}</code></td>
            <td>{event.resourceType}{event.resourceId ? <code className="secondary-code">{event.resourceId}</code> : null}</td>
            <td>{event.actorRef ? <code>{event.actorRef}</code> : 'Hệ thống'}</td>
            <td><StatusBadge tone={['success', 'succeeded', 'allowed'].includes(event.outcome.toLowerCase()) ? 'positive' : 'warning'}>{event.outcome}</StatusBadge></td>
            <td><code>{event.correlationId}</code></td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}
