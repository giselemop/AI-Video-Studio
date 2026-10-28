import { expect, test } from '@playwright/test'
import fs from 'node:fs'

const folder = 'C:/install/AI/Data/Qwen3Video20261022'

test('fresh ten-second Qwen narration preview plays to completion', async ({ page }) => {
  const run = JSON.parse(fs.readFileSync(`${folder}/run.json`, 'utf8'))
  const errors = []
  page.on('pageerror', e => errors.push(e.message))
  await page.goto(run.previewUrl)
  const video = page.getByLabel('Qwen中文配音10秒视频', { exact: true })
  await expect.poll(() => video.evaluate(v => v.readyState)).toBeGreaterThan(0)
  const actual = await video.evaluate(v => ({ width: v.videoWidth, height: v.videoHeight, duration: v.duration, muted: v.muted, volume: v.volume }))
  expect(actual.width).toBe(run.targetWidth)
  expect(actual.height).toBe(run.targetHeight)
  expect(Math.abs(actual.duration - 10)).toBeLessThan(.06)
  expect(actual.muted).toBe(false)
  expect(actual.volume).toBe(1)
  await page.getByRole('button', { name: '播放声画', exact: true }).click()
  await expect.poll(() => video.evaluate(v => v.currentTime)).toBeGreaterThan(.5)
  await expect.poll(() => video.evaluate(v => v.ended), { timeout: 20_000 }).toBe(true)
  const completion = await video.evaluate(v => ({ ended: v.ended, time: v.currentTime, error: v.error?.message || null, decodedFrames: v.getVideoPlaybackQuality().totalVideoFrames }))
  expect(completion.error).toBeNull()
  expect(completion.decodedFrames).toBeGreaterThan(100)
  expect(errors).toEqual([])
  await video.evaluate(v => {v.currentTime = 7.4})
  await expect.poll(() => video.evaluate(v => v.seeking)).toBe(false)
  await page.screenshot({ path: `${folder}/browser-preview.png`, fullPage: true })
  fs.writeFileSync(`${folder}/browser-playback.json`, JSON.stringify({ status: 'Passed', actual, completion, pageErrors: errors }, null, 2))
})

test('preview page rejects a path outside the generated artifact namespace', async ({ page }) => {
  let mediaRequested = false
  page.on('request', r => { if (r.url().includes('/api/media')) mediaRequested = true })
  await page.goto('http://127.0.0.1:18080/qwen3-video-preview.html?video=../../config/local.env')
  await expect(page.getByRole('status')).toContainText('视频路径无效')
  await expect(page.getByLabel('Qwen中文配音10秒视频', { exact: true })).not.toHaveAttribute('src')
  expect(mediaRequested).toBe(false)
})
