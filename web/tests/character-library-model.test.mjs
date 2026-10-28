import test from 'node:test'
import assert from 'node:assert/strict'
import { basicSlots, coverage, effectiveFraming, selectReference, coverReference, referenceLabel, orderedReferences } from '../src/components/characterLibraryModel.js'

const refs = basicSlots.map(([view, framing], index) => ({ referenceId: index + 1, view, framing, assetPath: `${view}-${framing}.png` }))
const version = { payload: { references: refs } }
test('front face and front full-body resolve to different stored references', () => {
  assert.equal(selectReference(version, 'front', 'closeUp').referenceId, 1)
  assert.equal(selectReference(version, 'front', 'fullBody').referenceId, 4)
  assert.equal(selectReference(version, 'front', 'medium'), undefined)
})
test('missing angle and framing never fall back to a different photo', () => {
  assert.equal(selectReference(version, 'back', 'closeUp'), undefined)
  assert.equal(selectReference(version, 'left', 'closeUp'), undefined)
})
test('nine unique required combinations complete the basic pack', () => {
  assert.deepEqual(coverage(refs), { present: 9, expected: 9, complete: true, missing: [] })
  assert.equal(coverage([...refs, refs[0]]).present, 9)
  assert.equal(coverage(refs.filter(r => r.framing === 'fullBody')).present, 6)
})
test('rear view absence remains a visible missing full-body slot', () => {
  const result = coverage(refs.filter(r => r.view !== 'back'))
  assert.equal(result.complete, false)
  assert.deepEqual(result.missing, [['back', 'fullBody']])
})
test('legacy views remain half-body without inventing a missing camera angle', () => {
  assert.equal(effectiveFraming({ view: 'front' }), 'medium')
  assert.equal(coverage([{ view: 'front' }, { view: 'fullBody' }]).present, 0)
  assert.equal(selectReference({ payload: { references: [{ view: 'front' }] } }, 'front', 'medium').view, 'front')
})
test('the card cover uses the face instead of the alphabetically first back view', () => {
  assert.equal(coverReference({ payload: { references: [...refs].reverse() } }).referenceId, 1)
  assert.equal(referenceLabel(refs[3]), '正面 · 全身')
})
test('gallery ordering shows three close-ups before six full-body images without mutating a version', () => {
  const reversed = [...refs].reverse()
  const ordered = orderedReferences({ payload: { references: reversed } })
  assert.deepEqual(ordered.map(r => r.referenceId), refs.map(r => r.referenceId))
  assert.equal(reversed[0].referenceId, 9)
})
