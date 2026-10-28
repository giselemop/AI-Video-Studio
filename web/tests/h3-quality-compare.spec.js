import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'

// This media acceptance test only reads the completed local run; it never submits work.
const reviewPath = process.env.H3_QUALITY_REVIEW
test.skip(!reviewPath, 'Requires a completed local H3 comparison review.json')

test('real H3 pair loads, plays and seeks together', async ({ page }, testInfo) => {
  const review = JSON.parse(readFileSync(reviewPath, 'utf8'))
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto(review.comparisonUrl)
  await expect(page.getByRole('status')).toContainText('已就绪')
  const geometry = await page.locator('video').evaluateAll(videos => videos.map(video => ({
    width: video.videoWidth, height: video.videoHeight, duration: video.duration
  })))
  expect(geometry[0].width).toBe(864)
  expect(geometry[0].height).toBe(480)
  expect(geometry[1].width).toBe(1376)
  expect(geometry[1].height).toBe(768)
  expect(geometry[0].duration).toBeCloseTo(124 / 24, 1)
  expect(geometry[1].duration).toBeCloseTo(geometry[0].duration, 2)
  await page.getByRole('button', { name: '播放对照', exact: true }).click()
  await expect.poll(async () => page.locator('#before').evaluate(video => video.ended), { timeout: 15_000 }).toBe(true)
  const decoded = await page.locator('video').evaluateAll(videos => videos.map(video => ({
    frames: video.getVideoPlaybackQuality().totalVideoFrames,
    dropped: video.getVideoPlaybackQuality().droppedVideoFrames
  })))
  expect(decoded.every(video => video.frames >= 120)).toBe(true)
  await page.locator('#seek').evaluate(input => {
    input.value = '2.5'
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
  await expect.poll(async () => page.locator('#after').evaluate(video => video.currentTime)).toBeCloseTo(2.5, 1)
  const positions = await page.locator('video').evaluateAll(videos => videos.map(video => video.currentTime))
  expect(Math.abs(positions[0] - positions[1])).toBeLessThan(0.042)
  await page.getByRole('slider', { name: 'H3 480p与768p分界线', exact: true }).evaluate(input => {
    input.value = '35'
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
  await expect(page.locator('#stage')).toHaveCSS('--split', '35%')
  await page.screenshot({ path: testInfo.outputPath('h3-quality-comparison.png'), fullPage: true })
  expect(errors).toEqual([])
  await testInfo.attach('real-media-probe', { body: JSON.stringify({ geometry, decoded, positions }), contentType: 'application/json' })
})

test('comparison rejects paths outside registered artifacts', async ({ page }) => {
  await page.goto('http://127.0.0.1:18080/h3-quality-compare.html?before=../../private.mp4&after=Artifacts/test.mp4')
  await expect(page.getByRole('status')).toContainText('缺少有效的视频路径')
  await expect(page.getByRole('button', { name: '播放对照', exact: true })).toBeDisabled()
})
