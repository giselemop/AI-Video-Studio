import {expect,test} from '@playwright/test'

test('pending comparison shows actual task state without enabling playback',async({page})=>{
  await page.route('**/api/**',r=>{
    const path=new URL(r.request().url()).pathname
    if(path==='/api/minimax/local/realistic-preview')return r.fulfill({json:{stage:'Generating20Steps',reference:null,video20:null,video30:null,finalVideo:null,task20:12345,task30:null}})
    if(path==='/api/tasks/12345')return r.fulfill({json:{task:{id:12345,status:'Running'}}})
    return r.fulfill({status:404,json:{error:'Unexpected fixture request'}})
  })
  await page.goto('/realistic-i2v-compare.html')
  await expect(page.locator('#s20')).toHaveText('任务 12345 · 生成中')
  await expect(page.getByRole('button',{name:'同步播放',exact:true})).toBeDisabled()
  await expect(page.getByLabel('写实优化10秒成片')).toBeHidden()
})

test('unsafe comparison manifest requests no media',async({page})=>{
  let media=false
  page.on('request',r=>{if(r.url().includes('/api/media'))media=true})
  await page.route('**/api/minimax/local/realistic-preview',r=>r.fulfill({json:{stage:'Prepared',reference:'../../config/local.env',video20:'Artifacts/test.mp4',video30:null}}))
  await page.goto('/realistic-i2v-compare.html')
  await expect(page.getByRole('status')).toContainText('路径无效')
  expect(media).toBe(false)
  expect(await page.locator('video').evaluateAll(vs=>vs.every(v=>!v.hasAttribute('src')))).toBe(true)
})

test('blocked content generation does not claim ongoing generation or a finished preview',async({page})=>{
  await page.route('**/api/minimax/local/realistic-preview',r=>r.fulfill({json:{stage:'Blocked',reference:null,video20:null,video30:null,finalVideo:null}}))
  await page.goto('/realistic-i2v-compare.html')
  await expect(page.getByRole('status')).toContainText('当前生成受阻，尚未完成新成片')
  await expect(page.getByRole('button',{name:'同步播放',exact:true})).toBeDisabled()
  await expect(page.getByLabel('写实优化10秒成片')).toBeHidden()
})

test('unsafe candidate gallery path is rejected before requesting any media',async({page})=>{
  let media=false;page.on('request',r=>{if(r.url().includes('/api/media'))media=true})
  await page.route('**/api/minimax/local/realistic-preview',r=>r.fulfill({json:{stage:'Blocked',referenceCandidates:[{candidate:4,path:'Artifacts/../../config/local.env.png'}]}}))
  await page.goto('/realistic-i2v-compare.html')
  await expect(page.getByRole('status')).toContainText('路径无效')
  expect(media).toBe(false)
})
