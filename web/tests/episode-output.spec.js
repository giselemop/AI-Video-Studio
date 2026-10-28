import { expect, test } from '@playwright/test'

async function json(response, description) {
  expect(response.ok(), `${description}: HTTP ${response.status()}`).toBeTruthy()
  return response.json()
}

async function login(page) {
  const username = process.env.AI_VIDEO_STUDIO_TEST_USERNAME
  const password = process.env.AI_VIDEO_STUDIO_TEST_PASSWORD
  if (!username || !password) throw new Error('需要 AI_VIDEO_STUDIO_TEST_USERNAME 与 AI_VIDEO_STUDIO_TEST_PASSWORD 执行受保护后台回归。')
  await page.goto('/#projects')
  await page.getByLabel('本机管理员账号').fill(username)
  await page.getByLabel('本机管理员密码').fill(password)
  await page.getByRole('button', { name: '登录后台', exact: true }).click()
  await expect(page.locator('.project-row').first()).toBeVisible()
}

async function findOutputEpisode(request) {
  const projects = await json(await request.get('/api/projects'), '读取项目列表')
  for (const project of projects) {
    const episodes = await json(await request.get(`/api/projects/${project.id}/episodes`), `读取项目 ${project.id} 的分集`)
    for (const episode of episodes) {
      const output = await json(await request.get(`/api/episodes/${episode.id}/output`), `读取分集 ${episode.id} 的正式输出`)
      if (output.latestVersion?.exists && output.latestVersion.actual?.hasAudio) return { project, episode, output }
    }
  }
  throw new Error('验收数据中没有可播放的正式 Episode 成片。')
}

async function findNotReadyEpisode(request) {
  const projects = await json(await request.get('/api/projects'), '读取项目列表')
  for (const project of projects) {
    const episodes = await json(await request.get(`/api/projects/${project.id}/episodes`), `读取项目 ${project.id} 的分集`)
    for (const episode of episodes) {
      const output = await json(await request.get(`/api/episodes/${episode.id}/output`), `读取分集 ${episode.id} 的正式输出`)
      if (output.source?.total > 0 && output.source.ready < output.source.total) return { project, episode, output }
    }
  }
  throw new Error('验收数据中没有“正式视频未就绪”的 Episode，无法验证合成阻断。')
}

async function findNoOutputEpisode(request) {
  const projects = await json(await request.get('/api/projects'), '读取项目列表')
  for (const project of projects) {
    const episodes = await json(await request.get(`/api/projects/${project.id}/episodes`), `读取项目 ${project.id} 的分集`)
    for (const episode of episodes) {
      const output = await json(await request.get(`/api/episodes/${episode.id}/output`), `读取分集 ${episode.id} 的正式输出`)
      if (!output.latestVersion && !output.activeTask) return { project, episode, output }
    }
  }
  throw new Error('验收数据中没有“尚未创建正式成片”的 Episode，无法验证空状态展示。')
}

async function findPreviewGateEpisode(request) {
  const projects = await json(await request.get('/api/projects'), '读取项目列表')
  for (const project of projects) {
    const episodes = await json(await request.get(`/api/projects/${project.id}/episodes`), `读取项目 ${project.id} 的分集`)
    for (const episode of episodes) {
      const output = await json(await request.get(`/api/episodes/${episode.id}/output`), `读取分集 ${episode.id} 的输出门禁`)
      if (output.canPreview && !output.canRender) return { project, episode, output }
    }
  }
  throw new Error('验收数据中没有“可生成审核预览但禁止正式合成”的 Episode。')
}

async function openProjectEpisode(page, candidate) {
  await page.goto('/#projects')
  await page.locator('.project-row').filter({ hasText: candidate.project.name }).first().click()
  await expect(page.locator('.project-detail > .panel-head h3')).toHaveText(candidate.project.name)

  const episodeTab = page.locator('.episode-tabs button').filter({ hasText: candidate.episode.name }).first()
  await expect(episodeTab).toBeVisible()
  await episodeTab.click()
  await expect(page.locator('.shot-board-head strong')).toHaveText(candidate.episode.name)

  const outputEntry = page.getByRole('button', { name: '查看整集结果', exact: true })
  await expect(outputEntry).toBeVisible()
  await expect(outputEntry).toBeEnabled()
  return outputEntry
}

test.describe('查看整集结果', () => {
  test('可从项目制作页打开正式成片、播放器和版本历史', async ({ page }) => {
    await login(page)
    const candidate = await findOutputEpisode(page.request)

    expect(candidate.output.outputStatus).toMatch(/Ready|Stale/)
    expect(candidate.output.source.ready).toBe(candidate.output.source.total)
    expect(candidate.output.latestVersion.actual?.durationSeconds).toBeGreaterThan(0)
    expect(candidate.output.latestVersion.actual?.hasAudio).toBeTruthy()

    const outputEntry = await openProjectEpisode(page, candidate)
    await outputEntry.click()

    const player = page.locator('video.episode-result-player')
    await expect(player).toBeVisible()
    await expect(player).toHaveAttribute('src', /\/api\/media\?assetPath=/)
    await expect(page.locator('.episode-version-row')).toHaveCount(candidate.output.versions.length)
    await expect(page.locator('.episode-output-dialog')).toContainText(`V${candidate.output.latestVersion.version}`)
  })

  test('镜头正式视频未就绪时拒绝创建整集合成任务', async ({ page }) => {
    await login(page)
    const candidate = await findNotReadyEpisode(page.request)
    const csrfToken = await page.context().cookies().then(cookies => cookies.find(cookie => cookie.name === 'ai_video_studio_csrf')?.value)
    const response = await page.request.post('/api/episode/render', { data: { episodeId: candidate.episode.id }, headers: { 'X-CSRF-Token': csrfToken || '' } })
    const body = await response.json()

    expect(response.status()).toBe(422)
    expect(body.error).toBeTruthy()
    expect(body.qualityGate.formalReady).toBeFalsy()
    expect(body.qualityGate.sources.filter(source => !source.formalReady).length).toBeGreaterThan(0)
  })

  test('尚未合成时仍可查看整集结果状态', async ({ page }) => {
    await login(page)
    const candidate = await findNoOutputEpisode(page.request)

    const outputEntry = await openProjectEpisode(page, candidate)
    await outputEntry.click()
    await expect(page.locator('.episode-output-dialog')).toBeVisible()
    await expect(page.locator('.episode-output-dialog')).toContainText('暂无正式成片')
  })

  test('快速切换项目不会让旧集输出覆盖当前分集', async ({ page }) => {
    await login(page)
    const completed = await findOutputEpisode(page.request)
    const empty = await findNoOutputEpisode(page.request)
    expect(String(completed.project.id)).not.toBe(String(empty.project.id))

    await page.goto('/#projects')
    await page.locator('.project-row').filter({ hasText: completed.project.name }).first().click()
    await page.locator('.project-row').filter({ hasText: empty.project.name }).first().click()
    await expect(page.locator('.project-detail > .panel-head h3')).toHaveText(empty.project.name)

    const episodeTab = page.locator('.episode-tabs button').filter({ hasText: empty.episode.name }).first()
    await expect(episodeTab).toBeVisible()
    await episodeTab.click()
    await expect(page.locator('.shot-board-head strong')).toHaveText(empty.episode.name)
    const outputEntry = page.getByRole('button', { name: '查看整集结果', exact: true })
    await expect(outputEntry).toBeEnabled()
    await outputEntry.click()
    await expect(page.locator('.episode-output-dialog')).toContainText('暂无正式成片')
  })

  test('项目制作页显示正式发布门禁和审核预览入口', async ({ page }) => {
    await login(page)
    const candidate = await findPreviewGateEpisode(page.request)

    await openProjectEpisode(page, candidate)

    const gate = page.locator('.episode-quality-gate-panel')
    await expect(gate).toBeVisible()
    await expect(gate).toContainText('Episode 发布门禁')
    await expect(gate).toContainText('正式合成已阻断')
    await expect(gate).toContainText(/镜头 QA \d+\/\d+/)
    const previewButton = gate.getByRole('button', { name: '生成审核预览（不作为正式成片）', exact: true })
    await expect(previewButton).toBeVisible()
    await expect(previewButton).toBeEnabled()
  })
})
