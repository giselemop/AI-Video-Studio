import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'

const reviewPath = process.env.H3_MOTION_REVIEW
test.skip(!reviewPath, 'Requires a completed local H3 motion take')

test('real native768 motion pair plays, loops, pauses and seeks', async ({ page }, testInfo) => {
  const review = JSON.parse(readFileSync(reviewPath, 'utf8'))
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto(review.comparisonUrl)
  await expect(page.getByRole('button', { name: '从头播放', exact: true })).toBeEnabled()
  const geometry = await page.locator('video').evaluateAll(videos => videos.map(video => ({
    width: video.videoWidth, height: video.videoHeight, duration: video.duration, loop: video.loop
  })))
  expect(geometry.every(video => video.width === 1376 && video.height === 768 && video.loop)).toBe(true)
  expect(geometry[0].duration).toBeCloseTo(124 / 24, 1)
  expect(geometry[1].duration).toBeCloseTo(geometry[0].duration, 2)
  await page.locator('video').evaluateAll(videos => videos.forEach(video => {
    let previous = video.currentTime
    video.dataset.observedLoops = '0'
    video.addEventListener('timeupdate', () => {
      if (previous > video.duration - .8 && video.currentTime < .8) {
        video.dataset.observedLoops = String(Number(video.dataset.observedLoops) + 1)
      }
      previous = video.currentTime
    })
  }))
  await page.getByRole('button', { name: '从头播放', exact: true }).click()
  await expect.poll(async () => page.locator('video').evaluateAll(videos => videos.every(video => !video.paused && video.currentTime > .3))).toBe(true)
  await expect.poll(async () => page.locator('video').evaluateAll(videos => videos.every(video => video.getVideoPlaybackQuality().totalVideoFrames >= 130)), { timeout: 15_000 }).toBe(true)
  await expect.poll(async () => page.locator('#before').evaluate(video => Number(video.dataset.observedLoops)), { timeout: 15_000 }).toBeGreaterThanOrEqual(1)
  await page.locator('#after').click()
  await expect.poll(async () => page.locator('video').evaluateAll(videos => videos.every(video => video.paused))).toBe(true)
  const presented = await page.evaluate(async () => {
    const videos = [...document.querySelectorAll('video')]
    const frames = videos.map(video => new Promise(resolve => {
      video.requestVideoFrameCallback((_, metadata) => resolve(metadata.mediaTime))
    }))
    const input = document.querySelector('#seek')
    input.value = '3.5'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    return Promise.all(frames)
  })
  await expect.poll(async () => page.locator('#after').evaluate(video => video.currentTime)).toBeCloseTo(3.5, 1)
  await expect.poll(async () => page.locator('video').evaluateAll(videos => videos.every(video => !video.seeking))).toBe(true)
  expect(presented.every(time => Math.abs(time - 3.5) < .042)).toBe(true)
  const playback = await page.locator('video').evaluateAll(videos => videos.map(video => ({
    time: video.currentTime, frames: video.getVideoPlaybackQuality().totalVideoFrames,
    dropped: video.getVideoPlaybackQuality().droppedVideoFrames, paused: video.paused,
    observedLoops: Number(video.dataset.observedLoops)
  })))
  expect(Math.abs(playback[0].time - playback[1].time)).toBeLessThan(.042)
  expect(errors).toEqual([])
  await page.screenshot({ path: testInfo.outputPath('h3-motion-comparison.png'), fullPage: true })
  await testInfo.attach('actual-motion-media', { body: JSON.stringify({ geometry, playback, presented }), contentType: 'application/json' })
})

test('motion comparison rejects an invalid media path', async ({ page }) => {
  await page.goto('http://127.0.0.1:18080/h3-motion-compare.html?before=../../private.mp4&after=Artifacts/test.mp4')
  await expect(page.getByRole('status')).toContainText('缺少有效的视频路径')
  await expect(page.getByRole('button', { name: '播放对照', exact: true })).toBeDisabled()
})
