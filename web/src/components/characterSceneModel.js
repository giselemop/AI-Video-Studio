export const sceneCamera = 'Eye-level locked camera, identical framing and fixed screen positions. No camera motion, zoom, crop or scene cut.'
export const sceneWorkflow = 'character-scene-klein4b-five-locked-1536-v1'
export const maskedSceneWorkflow = 'character-scene-klein4b-five-masked-locked-1536-v1'
export const defaultRegions = () => [
  { side:'left', x:300, y:50, width:420, height:814, feather:32 },
  { side:'right', x:820, y:8, width:430, height:856, feather:32 }
]
export const planSceneId = plan => plan?.payload?.sceneBinding?.versionId ?? null
export const sceneSelectionChanged = (plan, selected) => planSceneId(plan) !== (selected ?? null)
export function sceneCompositionIssues(version, shot, actors, roles) {
  if (!version) return []
  const p = version.payload, issues = []
  if (shot.shotFraming !== 'twoShot' || actors.length !== 2) issues.push('固定构图仅支持双人中景；请选择双人同框并绑定两位人物。')
  if (shot.scene !== p.sceneDescription || shot.camera !== p.camera) issues.push('场景或机位与冻结基准不同；请沿用基准，或另建机位版本。')
  if (actors.length === 2 && !actors.every(a => p.actorVersions.some(v => {
    const role = roles.find(r => r.role === a.role)
    return role && v.characterId === role.characterId && v.versionId === role.versionId && v.position === a.position
  }))) issues.push('人物造型版本或画面站位与基准不符；不会自动替换演员。')
  return issues
}
export function regionIssues(regions) {
  const issues = []
  if (regions.length !== 2 || !['left','right'].every(side => regions.filter(r => r.side === side).length === 1)) return ['人物区域必须各有一个画面左和画面右。']
  for (const r of regions) {
    if (![r.x,r.y,r.width,r.height,r.feather].every(Number.isInteger) || r.x < 0 || r.y < 0 || r.width < 64 || r.height < 64 || r.x+r.width > 1536 || r.y+r.height > 864) issues.push('人物区域须为整数且完整位于1536×864画布内，宽高至少64。')
    if (r.feather < 0 || r.feather > 64 || r.feather*2 >= Math.min(r.width,r.height)) issues.push('羽化须在0–64之间，并小于区域短边的一半。')
    if ((r.side === 'left' && r.x+r.width/2 >= 768) || (r.side === 'right' && r.x+r.width/2 <= 768)) issues.push('人物区域中心须位于对应的画面一侧。')
  }
  const [a,b] = regions
  if (a.x < b.x+b.width && b.x < a.x+a.width && a.y < b.y+b.height && b.y < a.y+a.height) issues.push('两个人物区域不能重叠。')
  if (regions.reduce((area,r) => area+r.width*r.height,0) > 1536*864*.65) issues.push('人物区域合计超过65%，须至少保留35%的固定背景。')
  return [...new Set(issues)]
}
