import {FoundationPanel} from '@/components/layout/foundation-panel';

export default function AuthorizationPage() {
  return (
    <FoundationPanel
      eyebrow="Authorization"
      title="Quản trị quyền workforce"
      description="Capability catalog do code định nghĩa; role và assignment được quản lý động qua NestJS. Portal không tự cấp quyền."
      requiredCapability="authorization.role.read"
    />
  );
}
