import {expect, test} from '@playwright/test';

test('redirects a workforce route without an opaque session', async ({page}) => {
  await page.goto('/authorization/roles');
  await expect(page).toHaveURL(/\/sign-in\?returnTo=%2Fauthorization%2Froles/);
  await expect(page.getByRole('heading', {name: 'Đăng nhập dành cho nhân sự'}))
    .toBeVisible();
});

test('renders the public workforce entry without exposing a fake login', async ({page}) => {
  await page.goto('/');
  await expect(page.getByRole('heading', {
    name: 'Không gian làm việc của đội ngũ VFBiz',
  })).toBeVisible();
  await expect(page.getByText('Không lưu token trong trình duyệt')).toBeVisible();
});
