import {
  hasAllCapabilities,
  type WorkforceEntitlements,
} from '@/platform/api/entitlements';

export interface WorkforceNavigationItem {
  readonly href: string;
  readonly label: string;
  readonly requiredCapabilities: readonly string[];
}

const workforceNavigation: readonly WorkforceNavigationItem[] = [
  {
    href: '/authorization/roles',
    label: 'Role',
    requiredCapabilities: ['authorization.role.read'],
  },
  {
    href: '/authorization/assignments',
    label: 'Phân công quyền',
    requiredCapabilities: ['authorization.assignment.read'],
  },
  {
    href: '/authorization/approvals',
    label: 'Yêu cầu phê duyệt',
    requiredCapabilities: ['authorization.approval.read'],
  },
  {
    href: '/audit',
    label: 'Audit',
    requiredCapabilities: ['audit.event.read'],
  },
] as const;

export function visibleNavigation(
  entitlements: WorkforceEntitlements,
): readonly WorkforceNavigationItem[] {
  return workforceNavigation.filter((item) =>
    hasAllCapabilities(entitlements, item.requiredCapabilities),
  );
}
