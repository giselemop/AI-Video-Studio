import { expect, test } from '@playwright/test'

// Isolated UI fixtures: every API request is intercepted, never the real task queue.
async function fixture(page, ready = false, loginRequired = true) {
  const state = {
    posts: [],
    failFirst: false,
    history: [],
    status: {
      modelsPresent: ready, modelsVerified: ready, workflowId: ready ? 9 : null,
      comfyOnline: true, queue: { enabled: true, paused: false },
      downloadedBytes: ready ? 100 : 20, totalBytes: 100,
      assets: [{ role: 'diffusion', file: 'local-model.gguf', expectedBytes: 100, downloadedBytes: ready ? 100 : 20, present: ready, verified: ready }]
    }
  }
  await page.route('**/api/**', async route => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname
    let data
    let status = 200
    if (path === '/api/auth/status') data = { configured: true, authenticated: loginRequired, loginRequired, accessMode: loginRequired ? 'Password' : 'LocalOnly', username: loginRequired ? 'fixture-user' : 'local-operator', role: loginRequired ? 'Administrator' : 'LocalOperator', csrfToken: 'fixture-csrf' }
    else if (path === '/api/health') data = { database: { online: true }, comfy: { online: true } }
    else if (path === '/api/projects') data = [{ id: 9, name: '基准项目' }, { id: 10, name: '第二项目' }]
    else if (path === '/api/minimax/local/status') data = state.status
    else if (path === '/api/minimax/local/history') data = state.history
    else if (path === '/api/minimax/local/register') data = { registered: true }
    else if (path === '/api/minimax/local/verify') data = { verified: true }
    else if (path === '/api/minimax/local/reference') data = { assetPath: 'Projects/9/MiniMaxReferences/frame.png' }
    else if (path === '/api/minimax/local/video') {
      state.posts.push({ key: request.headers()['idempotency-key'], body: request.postDataJSON() })
      if (state.failFirst && state.posts.length === 1) { status = 503; data = { error: '测试夹具：响应暂不可用' } }
      else {
        state.history = [{ id: 61, seed: '123', status: 'Pending', provider: 'MiniMaxLocal', createdAt: '2026-10-18 16:00:00' }]
        data = { id: 61, status: 'Pending' }
      }
    } else if (path === '/api/tasks/61') data = { task: { id: 61, status: 'Pending', progress: 0 }, results: [] }
    else if (path === '/api/media') return route.fulfill({ status: 200, contentType: 'image/png', body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/amcAAAAASUVORK5CYII=', 'base64') })
    else { status = 404; data = { error: `Unexpected fixture request: ${path}` } }
    await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) })
  })
  await page.goto('/#minimax')
  await expect(page.getByRole('heading', { name: '先做一条有声音的短片' })).toBeVisible()
  return state
}

test('incomplete models show actual download progress and block generation', async ({ page }) => {
  const state = await fixture(page)
  await expect(page.getByRole('button', { name: '生成视频与声音', exact: true })).toBeDisabled()
  await expect(page.getByRole('button', { name: '校验并准备本地生成', exact: true })).toBeDisabled()
  await expect(page.locator('.minimax-page .el-progress__text')).toContainText('20%')
  expect(state.posts).toHaveLength(0)
  await expect(page.getByText('无需 API Key。', { exact: false })).toBeVisible()
})

test('local-only mode opens the workbench without a password prompt', async ({ page }) => {
  await fixture(page, false, false)
  await expect(page.getByRole('heading', { name: '登录本机后台' })).toHaveCount(0)
  await expect(page.getByText('本机免登录', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '退出登录', exact: true })).toHaveCount(0)
})

test('explicit frame and project are retained; a lost response reuses the submission key', async ({ page }) => {
  const state = await fixture(page, true)
  state.failFirst = true
  await page.getByRole('combobox', { name: '素材归属项目', exact: true }).focus()
  await page.getByRole('combobox', { name: '素材归属项目', exact: true }).press('ArrowDown')
  await page.getByRole('option', { name: '基准项目', exact: true }).click()
  await page.getByLabel('上传 MiniMax 首帧').setInputFiles({ name: 'frame.png', mimeType: 'image/png', buffer: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/amcAAAAASUVORK5CYII=', 'base64') })
  await expect(page.getByAltText('当前首帧')).toBeVisible()
  await page.getByPlaceholder('描述一个能在短片内完成的动作。需要对白时明确人物、台词、语气；不需要对白时写明环境声、无对白。').fill('人物微笑并轻轻挥手，说“你好”，语气平静。')
  const submit = page.getByRole('button', { name: '生成视频与声音', exact: true })
  await expect(submit).toBeEnabled()
  await submit.click()
  await expect(page.getByText('测试夹具：响应暂不可用', { exact: true })).toBeVisible()
  await expect(submit).toBeEnabled()
  await submit.click()
  await expect(page.getByText('任务 #61 · Pending')).toBeVisible()
  expect(state.posts).toHaveLength(2)
  expect(state.posts[0].key).toBeTruthy()
  expect(state.posts[0].key).toBe(state.posts[1].key)
  expect(state.posts[1].body.projectId).toBe(9)
  expect(state.posts[1].body.inputImagePath).toBe('Projects/9/MiniMaxReferences/frame.png')
  expect(state.posts[1].body.prompt).toContain('你好')
})

test('changing the project clears the old frame binding', async ({ page }) => {
  await fixture(page, true)
  await page.getByRole('combobox', { name: '素材归属项目', exact: true }).focus()
  await page.getByRole('combobox', { name: '素材归属项目', exact: true }).press('ArrowDown')
  await page.getByRole('option', { name: '基准项目', exact: true }).click()
  await page.getByLabel('上传 MiniMax 首帧').setInputFiles({ name: 'frame.png', mimeType: 'image/png', buffer: Buffer.from('fixture-image') })
  await expect(page.getByAltText('当前首帧')).toBeVisible()
  await page.getByRole('combobox', { name: '素材归属项目', exact: true }).focus()
  await page.getByRole('combobox', { name: '素材归属项目', exact: true }).press('ArrowDown')
  await page.getByRole('option', { name: '第二项目', exact: true }).click()
  await expect(page.getByAltText('当前首帧')).toHaveCount(0)
  await expect(page.getByRole('button', { name: '生成视频与声音', exact: true })).toBeDisabled()
})

test('768p is explicitly selected and sent without changing the default route', async ({ page }) => {
  const state = await fixture(page, true)
  state.status.generationProfiles = [
    { id: 'baseline480', label: '480p 基线', width: 864, height: 480, workflowId: 9 },
    { id: 'quality768', label: '768p 画质实验', width: 1376, height: 768, workflowId: 10 }
  ]
  await page.getByRole('button', { name: '刷新状态', exact: true }).click()
  await expect(page.getByText('864×480、24 FPS、20步。', { exact: false })).toBeVisible()
  await page.getByRole('combobox', { name: '素材归属项目', exact: true }).focus()
  await page.getByRole('combobox', { name: '素材归属项目', exact: true }).press('ArrowDown')
  await page.getByRole('option', { name: '基准项目', exact: true }).click()
  await page.getByLabel('上传 MiniMax 首帧').setInputFiles({ name: 'frame.png', mimeType: 'image/png', buffer: Buffer.from('fixture-image') })
  await page.getByPlaceholder('描述一个能在短片内完成的动作。需要对白时明确人物、台词、语气；不需要对白时写明环境声、无对白。').fill('静态校园镜头，树叶轻动，只有自然环境声。')
  await page.getByRole('combobox', { name: 'H3 生成规格', exact: true }).focus()
  await page.getByRole('combobox', { name: 'H3 生成规格', exact: true }).press('ArrowDown')
  await page.getByRole('option', { name: '768p 画质实验 · 1376×768', exact: true }).click()
  await expect(page.getByText('1376×768、24 FPS、20步。', { exact: false })).toBeVisible()
  await page.getByRole('button', { name: '生成视频与声音', exact: true }).click()
  await expect(page.getByText('任务 #61 · Pending')).toBeVisible()
  expect(state.posts[0].body.profile).toBe('quality768')
})

test('native1080 is explicit and preserves the default while displaying the crop', async ({ page }) => {
  const state = await fixture(page, true)
  state.status.generationProfiles = [
    { id: 'baseline480', label: '480p 基线', width: 864, height: 480, workflowId: 9 },
    { id: 'native1080', label: '1080p 原生实验', width: 1920, height: 1088, workflowId: 11 }
  ]
  await page.getByRole('button', { name: '刷新状态', exact: true }).click()
  await expect(page.getByText('864×480、24 FPS、20步。', { exact: false })).toBeVisible()
  await page.getByRole('combobox', { name: '素材归属项目', exact: true }).focus()
  await page.getByRole('combobox', { name: '素材归属项目', exact: true }).press('ArrowDown')
  await page.getByRole('option', { name: '基准项目', exact: true }).click()
  await page.getByLabel('上传 MiniMax 首帧').setInputFiles({ name: 'frame.png', mimeType: 'image/png', buffer: Buffer.from('fixture-image') })
  await page.getByPlaceholder('描述一个能在短片内完成的动作。需要对白时明确人物、台词、语气；不需要对白时写明环境声、无对白。').fill('静态校园镜头，树叶轻动，只有自然环境声。')
  await page.getByRole('combobox', { name: 'H3 生成规格', exact: true }).focus()
  await page.getByRole('combobox', { name: 'H3 生成规格', exact: true }).press('ArrowDown')
  await page.getByRole('option', { name: '1080p 原生实验 · 1920×1088', exact: true }).click()
  await expect(page.getByText('1920×1088、24 FPS、20步。', { exact: false })).toBeVisible()
  await expect(page.getByText('工作流上下各裁4行输出1920×1080。', { exact: false })).toBeVisible()
  await page.getByRole('button', { name: '生成视频与声音', exact: true }).click()
  await expect(page.getByText('任务 #61 · Pending')).toBeVisible()
  expect(state.posts[0].body.profile).toBe('native1080')
  expect(state.posts[0].body.steps).toBe(20)
})

test('30 steps is explicit for native1080 and resets on a profile change', async ({ page }) => {
  const state = await fixture(page, true)
  state.status.generationProfiles = [
    { id: 'baseline480', label: '480p 基线', width: 864, height: 480, workflowId: 9 },
    { id: 'native1080', label: '1080p 原生实验', width: 1920, height: 1088, workflowId: 11 }
  ]
  await page.getByRole('button', { name: '刷新状态', exact: true }).click()
  const profile = page.getByRole('combobox', { name: 'H3 生成规格', exact: true })
  await profile.focus(); await profile.press('ArrowDown')
  await page.getByRole('option', { name: '1080p 原生实验 · 1920×1088', exact: true }).click()
  const steps = page.getByRole('combobox', { name: 'H3 采样步数', exact: true })
  await steps.focus(); await steps.press('ArrowDown')
  await page.getByRole('option', { name: '30步 · 同首帧画质对照', exact: true }).click()
  await expect(page.getByText('1920×1088、24 FPS、30步。', { exact: false })).toBeVisible()
  await profile.focus(); await profile.press('ArrowDown')
  await page.getByRole('option', { name: '480p 基线 · 864×480', exact: true }).click()
  await expect(page.getByText('864×480、24 FPS、20步。', { exact: false })).toBeVisible()
  await expect(steps).toHaveCount(0)
})
