import { expect, test } from '@playwright/test'

test('Qwen voice workbench submits an instruction and plays the registered audio', async ({ page }) => {
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    let data = []
    if (path === '/api/auth/status') data = { configured: true, authenticated: false, loginRequired: false, role: 'LocalOperator', csrfToken: 'fixture' }
    else if (path === '/api/health') data = { database: { online: true }, comfy: { online: true } }
    else if (path === '/api/dashboard') data = { counts: {}, recentTasks: [] }
    else if (path === '/api/projects') data = [{ id: 28, name: '中文配音测试' }]
    else if (path === '/api/audio/voices') data = { available: true, qwenAvailable: true, voices: [{ id: 'qwen3:Vivian', name: 'Vivian · 中文女声', engine: 'Qwen3TTS', available: true }] }
    else if (path === '/api/audio/tts') {
      const body = route.request().postDataJSON()
      expect(body.voiceId).toBe('qwen3:Vivian')
      expect(body.projectId).toBe(28)
      expect(body.instruction).toContain('温柔')
      data = { taskId: 42, status: 'Pending' }
    } else if (path === '/api/tasks/42') data = { task: { id: 42, status: 'Succeeded', taskType: 'Audio', durationMs: 2000 }, results: [{ available: true, mimeType: 'audio/wav', durationSeconds: 12, assetPath: 'fixture/voice.wav', mediaUrl: '/fixture/voice.wav' }] }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) })
  })
  await page.goto('/#voice')
  await expect(page.getByRole('heading', { name: '声音工作台' })).toBeVisible()
  await expect(page.getByLabel('演绎指令', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '生成中文配音', exact: true }).click()
  await expect(page.getByLabel('中文配音试听', { exact: true })).toHaveAttribute('src', '/fixture/voice.wav')
  await expect(page.getByText('配音已生成', { exact: true })).toBeVisible()
})

test('Unavailable local model prevents a new Qwen generation', async ({ page }) => {
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    let data = []
    if (path === '/api/auth/status') data = { configured: true, authenticated: false, loginRequired: false, csrfToken: 'fixture' }
    else if (path === '/api/health') data = { database: { online: true }, comfy: { online: true } }
    else if (path === '/api/dashboard') data = { counts: {}, recentTasks: [] }
    else if (path === '/api/projects') data = [{ id: 28, name: '中文配音测试' }]
    else if (path === '/api/audio/voices') data = { qwenAvailable: false, qwenMessage: '模型下载尚未完成', voices: [] }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) })
  })
  await page.goto('/#voice')
  await expect(page.getByRole('button', { name: '生成中文配音', exact: true })).toBeDisabled()
  await expect(page.getByText('模型下载尚未完成', { exact: true })).toBeVisible()
})
