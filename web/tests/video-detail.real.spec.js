import { expect, test } from '@playwright/test'
import fs from 'node:fs'

const folder='C:/install/AI/Data/SeedVR2Enhancement20261022'
const url='http://127.0.0.1:18080/video-detail-compare.html'

test('three sample versions seek together and play with one narration track', async ({page})=>{
  const errors=[];page.on('pageerror',e=>errors.push(e.message))
  await page.goto(url)
  await expect(page.getByRole('button',{name:'同步播放',exact:true})).toBeEnabled()
  const videos=page.locator('video')
  expect(await videos.count()).toBe(3)
  const actual=await videos.evaluateAll(vs=>vs.map(v=>({width:v.videoWidth,height:v.videoHeight,duration:v.duration,muted:v.muted})))
  expect(actual.map(v=>[v.width,v.height])).toEqual([[1920,1080],[1920,1080],[1920,1080]])
  expect(actual.map(v=>v.muted)).toEqual([true,true,false])
  await page.getByLabel('对照帧',{exact:true}).fill('24')
  await expect.poll(()=>videos.evaluateAll(vs=>vs.every(v=>!v.seeking))).toBe(true)
  const seeked=await videos.evaluateAll(vs=>vs.map(v=>v.currentTime))
  expect(seeked.map((t,i)=>Math.abs(t-(i<2?7:1))<.03)).toEqual([true,true,true])
  await page.getByRole('button',{name:'回到开头',exact:true}).click()
  await page.getByRole('button',{name:'同步播放',exact:true}).click()
  await expect.poll(()=>page.locator('#c').evaluate(v=>v.currentTime)).toBeGreaterThan(.5)
  const drift=await videos.evaluateAll(vs=>Math.max(...vs.map((v,i)=>v.currentTime-(i<2?6:0)))-Math.min(...vs.map((v,i)=>v.currentTime-(i<2?6:0))))
  expect(drift).toBeLessThan(.16)
  await expect.poll(()=>page.locator('#c').evaluate(v=>v.ended),{timeout:8000}).toBe(true)
  await expect.poll(()=>videos.evaluateAll(vs=>vs.every(v=>v.paused))).toBe(true)
  await page.getByLabel('对照帧',{exact:true}).fill('36')
  await page.getByRole('button',{name:'局部放大',exact:true}).click()
  await expect(page.getByRole('button',{name:'局部放大',exact:true})).toHaveAttribute('aria-pressed','true')
  await expect.poll(()=>videos.evaluateAll(vs=>vs.every(v=>!v.seeking))).toBe(true)
  await page.screenshot({path:`${folder}/browser-sample-zoom.png`,fullPage:true})
  await page.getByRole('button',{name:'局部放大',exact:true}).click()
  await page.screenshot({path:`${folder}/browser-sample.png`,fullPage:true})
  expect(await videos.evaluateAll(vs=>vs.map(v=>v.error?.message||null))).toEqual([null,null,null])
  expect(errors).toEqual([])
  fs.writeFileSync(`${folder}/browser-sample.json`,JSON.stringify({status:'Passed',actual,seeked,drift,pageErrors:errors},null,2))
})

test('all three full versions play to ten seconds',async({page})=>{
  const state=JSON.parse(fs.readFileSync(`${folder}/run.json`,'utf8'))
  test.skip(!state.fullFinalTaskIdPath,'Full audio preservation is still running')
  await page.goto(url)
  await expect(page.getByRole('button',{name:'完整10秒',exact:true})).toBeEnabled()
  await page.getByRole('button',{name:'完整10秒',exact:true}).click()
  await expect(page.locator('#status')).toContainText('完整10秒')
  await page.getByRole('button',{name:'同步播放',exact:true}).click()
  await expect.poll(()=>page.locator('#c').evaluate(v=>v.ended),{timeout:20000}).toBe(true)
  const completion=await page.locator('video').evaluateAll(vs=>vs.map(v=>({time:v.currentTime,ended:v.ended,decodedFrames:v.getVideoPlaybackQuality().totalVideoFrames,error:v.error?.message||null})))
  for(const v of completion){expect(v.time).toBeGreaterThan(9.9);expect(v.error).toBeNull();expect(v.decodedFrames).toBeGreaterThan(230)}
  await page.getByLabel('对照帧',{exact:true}).fill('180')
  await expect.poll(()=>page.locator('video').evaluateAll(vs=>vs.every(v=>!v.seeking))).toBe(true)
  await page.screenshot({path:`${folder}/browser-full.png`,fullPage:true})
  fs.writeFileSync(`${folder}/browser-full.json`,JSON.stringify({status:'Passed',completion},null,2))
})

test('invalid manifest path is rejected before requesting any media',async({page})=>{
  let requested=false
  page.on('request',r=>{if(r.url().includes('/api/media'))requested=true})
  await page.route('**/api/video-restore/comparison',r=>r.fulfill({json:{original:'../../config/local.env',onePass:'Artifacts/test.mp4',restoredSample:'Artifacts/test.mp4'}}))
  await page.goto(url)
  await expect(page.locator('#status')).toContainText('视频路径无效')
  expect(requested).toBe(false)
  expect(await page.locator('video').evaluateAll(vs=>vs.every(v=>!v.hasAttribute('src')))).toBe(true)
})
