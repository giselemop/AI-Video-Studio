import { expect, test } from '@playwright/test'
import fs from 'node:fs'

const evidence = 'C:/install/AI/Data/Qwen3Tts20261022'

test('deployed Qwen sample loads and actually plays in the voice workbench', async ({ page }) => {
  const run = JSON.parse(fs.readFileSync(`${evidence}/run.json`, 'utf8'))
  expect(run.stage).toBe('ReadyForUserPreview')
  await page.goto('http://127.0.0.1:18080/#voice')
  await expect(page.getByRole('heading', { name: '声音工作台' })).toBeVisible()
  await expect(page.getByText('Qwen3-TTS 本地就绪', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: `任务 ${run.taskId}`, exact: true }).click()
  const player = page.getByLabel('中文配音试听', { exact: true })
  await expect(player).toHaveAttribute('src', run.audio.mediaUrl)
  await expect.poll(() => player.evaluate(el => el.readyState)).toBeGreaterThan(0)
  const duration = await player.evaluate(el => el.duration)
  expect(Math.abs(duration - run.durationSeconds)).toBeLessThan(0.1)
  await player.evaluate(el => el.play())
  await expect.poll(() => player.evaluate(el => el.currentTime)).toBeGreaterThan(0.5)
  const playback = await player.evaluate(el => ({ currentTime: el.currentTime, paused: el.paused, duration: el.duration, error: el.error?.message || null }))
  expect(playback.paused).toBe(false)
  expect(playback.error).toBeNull()
  await expect.poll(() => player.evaluate(el => el.ended), { timeout: 20_000 }).toBe(true)
  const completed = await player.evaluate(el => ({ currentTime: el.currentTime, ended: el.ended, error: el.error?.message || null }))
  expect(completed.error).toBeNull()
  await page.screenshot({ path: `${evidence}/voice-workbench.png`, fullPage: true })
  fs.writeFileSync(`${evidence}/browser-playback.json`, JSON.stringify({ status: 'Passed', taskId: run.taskId, ...playback, completed }, null, 2))
})
