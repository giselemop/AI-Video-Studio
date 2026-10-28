import { expect, test } from '@playwright/test'

async function login(page) {
  const username = process.env.AI_VIDEO_STUDIO_TEST_USERNAME
  const password = process.env.AI_VIDEO_STUDIO_TEST_PASSWORD
  if (!username || !password) throw new Error('需要 AI_VIDEO_STUDIO_TEST_USERNAME 与 AI_VIDEO_STUDIO_TEST_PASSWORD 执行受保护后台回归。')
  await page.goto('/#characters')
  await page.getByLabel('本机管理员账号').fill(username)
  await page.getByLabel('本机管理员密码').fill(password)
  await page.getByRole('button', { name: '登录后台', exact: true }).click()
  await expect(page.getByRole('heading', { name: '角色资产库' })).toBeVisible()
}

test('角色资产与编辑弹窗不显示乱码，并显示真实服务状态', async ({ page }) => {
  await login(page)

  await expect(page.getByRole('heading', { name: '角色资产库' })).toBeVisible()
  await expect(page.getByText('ComfyUI 在线', { exact: true })).toBeVisible()
  await expect(page.getByText(/NVIDIA GeForce RTX 4070.*MiB 空闲/)).toBeVisible()

  const qaAdultCard = page.locator('article').filter({ hasText: 'QA-Adult-01' })
  await expect(qaAdultCard.getByText('椭圆偏方脸、暖棕色眼睛、挺直鼻梁、薄而自然的嘴唇、左眼下小痣')).toBeVisible()
  await expect(qaAdultCard.getByText('黑色短发侧分，短而整齐的胡须')).toBeVisible()

  await qaAdultCard.getByRole('button', { name: '编辑', exact: true }).click()
  await expect(page.getByRole('dialog', { name: '编辑角色资产' })).toBeVisible()
  await expect(page.getByLabel('年龄设定')).toHaveValue('32 岁成年东亚男性')
  await expect(page.getByLabel('身体比例')).toHaveValue('匀称偏修长')
  await expect(page.getByLabel('脸部特征')).toHaveValue('椭圆偏方脸、暖棕色眼睛、挺直鼻梁、薄而自然的嘴唇、左眼下小痣')

  await expect.poll(async () => page.locator('body').innerText()).not.toMatch(/\?{2,}/)
})
