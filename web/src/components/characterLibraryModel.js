export const viewNames = { front: '正面', threeQuarterLeft: '左前侧', left: '左侧', threeQuarterBackLeft: '左后侧', back: '背面', threeQuarterBackRight: '右后侧', right: '右侧', threeQuarterRight: '右前侧', fullBody: '旧版全身（方向未标注）' }
export const framingNames = { closeUp: '面部近景', medium: '半身', fullBody: '全身' }
export const captureViews = Object.keys(viewNames).filter(view => view !== 'fullBody')
export const basicSlots = [['front', 'closeUp'], ['threeQuarterLeft', 'closeUp'], ['threeQuarterRight', 'closeUp'], ['front', 'fullBody'], ['threeQuarterLeft', 'fullBody'], ['left', 'fullBody'], ['back', 'fullBody'], ['right', 'fullBody'], ['threeQuarterRight', 'fullBody']]
export function effectiveFraming(reference) { return reference.framing || (reference.view === 'fullBody' ? 'fullBody' : 'medium') }
export function referenceKey(view, framing) { return `${view}:${framing}` }
export function selectReference(version, view, framing) { return version?.payload.references.find(reference => reference.view === view && effectiveFraming(reference) === framing) }
export function coverReference(version) { const refs = version?.payload.references || []; return refs.find(r => r.view === 'front' && effectiveFraming(r) === 'closeUp') || refs.find(r => r.view === 'front') || refs[0] }
export function coverage(references = []) { const keys = new Set(references.map(r => referenceKey(r.view, effectiveFraming(r)))); const missing = basicSlots.filter(([view, framing]) => !keys.has(referenceKey(view, framing))); return { present: basicSlots.length - missing.length, expected: basicSlots.length, complete: missing.length === 0, missing } }
export function referenceLabel(reference) { return `${viewNames[reference.view] || reference.view} · ${framingNames[effectiveFraming(reference)] || effectiveFraming(reference)}` }
export function orderedReferences(version) { const rank = new Map(basicSlots.map(([view, framing], index) => [referenceKey(view, framing), index])); return [...(version?.payload.references || [])].sort((a, b) => (rank.get(referenceKey(a.view, effectiveFraming(a))) ?? 99) - (rank.get(referenceKey(b.view, effectiveFraming(b))) ?? 99)) }
