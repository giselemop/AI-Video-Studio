import test from 'node:test'
import assert from 'node:assert/strict'
import {defaultRegions,regionIssues,sceneSelectionChanged,sceneCompositionIssues,sceneCamera} from '../src/components/characterSceneModel.js'

const scene={id:29,payload:{camera:sceneCamera,sceneDescription:'Reading room',actorVersions:[{characterId:19,versionId:4,position:'left'},{characterId:20,versionId:5,position:'right'}]}}
const shot={camera:sceneCamera,scene:'Reading room',shotFraming:'twoShot'}
const actors=[{role:'林安',position:'left'},{role:'周言',position:'right'}]
const roles=[{role:'林安',characterId:19,versionId:4},{role:'周言',characterId:20,versionId:5}]
test('legacy plans remain unchanged without an explicit scene selection',()=>{
  assert.equal(sceneSelectionChanged({payload:{}},null),false)
  assert.equal(sceneSelectionChanged({payload:{}},undefined),false)
  assert.equal(sceneSelectionChanged({payload:{}},29),true)
  assert.deepEqual(sceneCompositionIssues(null,shot,actors,roles),[])
})
test('changing or clearing a frozen scene requires a new Shot plan',()=>{
  const plan={payload:{sceneBinding:{versionId:29}}}
  assert.equal(sceneSelectionChanged(plan,29),false)
  assert.equal(sceneSelectionChanged(plan,38),true)
  assert.equal(sceneSelectionChanged(plan,null),true)
})
test('a scene cannot silently adopt a new actor version or swapped positions',()=>{
  assert.deepEqual(sceneCompositionIssues(scene,shot,actors,roles),[])
  assert.ok(sceneCompositionIssues(scene,shot,actors,[{...roles[0],versionId:6},roles[1]]).length)
  assert.ok(sceneCompositionIssues(scene,shot,[{...actors[0],position:'right'},{...actors[1],position:'left'}],roles).length)
  assert.ok(sceneCompositionIssues(scene,shot,actors,[]).length)
})
test('fixed composition rejects a camera cut, new room, and a single-person framing',()=>{
  for(const change of [{camera:'Pan right'},{scene:'Different room'},{shotFraming:'closeUp'}])assert.ok(sceneCompositionIssues(scene,{...shot,...change},actors,roles).length)
  assert.ok(sceneCompositionIssues(scene,shot,actors.slice(0,1),roles).length)
})
test('actor masks protect the canvas and background; caller edits do not change defaults',()=>{
  assert.deepEqual(regionIssues(defaultRegions()),[])
  const wider=[{side:'left',x:270,y:32,width:480,height:832,feather:32},{side:'right',x:770,y:0,width:500,height:864,feather:32}]
  assert.deepEqual(regionIssues(wider),[])
  for(const change of [{x:-1},{width:2000},{x:300.5},{feather:65},{height:63}]){const r=defaultRegions();Object.assign(r[0],change);assert.ok(regionIssues(r).length)}
  const overlap=defaultRegions();overlap[1].x=650;assert.ok(regionIssues(overlap).length)
  const large=[{side:'left',x:0,y:0,width:760,height:864,feather:32},{side:'right',x:776,y:0,width:760,height:864,feather:32}];assert.ok(regionIssues(large).length)
  const r=defaultRegions();r[0].x=99;assert.equal(defaultRegions()[0].x,300)
})
