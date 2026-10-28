import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'

const report = process.env.H3_CAMPUS_STORY_REPORT
test.skip(!report, 'Requires an actual completed story assembly')

test('actual campus story plays all five chapters at native1080/24', async ({ page }, testInfo) => {
  test.setTimeout(65000)
  const run = JSON.parse(readFileSync(report, 'utf8'))
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto(run.previewUrl)
  await expect(page.getByRole('button', { name: '1 · 发现', exact: true })).toBeEnabled()
  const geometry = await page.locator('video').evaluate(v => ({ width: v.videoWidth, height: v.videoHeight, duration: v.duration }))
  expect(geometry.width).toBe(1920)
  expect(geometry.height).toBe(1080)
  expect(geometry.duration).toBeCloseTo(620/24, 1)
  await page.locator('video').evaluate(v => v.play())
  await expect.poll(async () => page.locator('video').evaluate(v => v.ended), { timeout: 35000 }).toBe(true)
  await expect(page.getByRole('status')).toContainText('已播放完毕')
  const playback = await page.locator('video').evaluate(v => ({ frames: v.getVideoPlaybackQuality().totalVideoFrames, dropped: v.getVideoPlaybackQuality().droppedVideoFrames }))
  expect(playback.frames).toBeGreaterThanOrEqual(618)
  const presented = []
  for (let n=0; n<5; n++) {
    const time = await page.evaluate(async n => {
      const v=document.querySelector('video')
      const frame=new Promise(resolve=>v.requestVideoFrameCallback((_,m)=>resolve(m.mediaTime)))
      document.querySelector(`[data-shot="${n}"]`).click()
      return frame
    },n)
    expect(Math.abs(time-n*124/24)).toBeLessThan(.043)
    presented.push(time)
  }
  expect(errors).toEqual([])
  await page.screenshot({path:testInfo.outputPath('actual-campus-story.png'),fullPage:true})
  await testInfo.attach('actual-story-playback', {body:JSON.stringify({geometry,playback,presented}),contentType:'application/json'})
})

test('story preview rejects path traversal before loading media', async ({ page }) => {
  const requested=[]
  page.on('request',request=>{if(request.url().includes('/api/media'))requested.push(request.url())})
  await page.goto('http://127.0.0.1:18080/h3-campus-story-preview.html?video=Artifacts/../../private.mp4')
  await expect(page.getByRole('status')).toContainText('视频路径无效')
  await expect(page.getByRole('button', { name: '1 · 发现', exact: true })).toBeDisabled()
  expect(requested).toEqual([])
})
