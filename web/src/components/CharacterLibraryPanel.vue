<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import CharacterWorkshopPanel from './CharacterWorkshopPanel.vue'
import { viewNames, framingNames, captureViews, effectiveFraming, referenceKey, selectReference, coverReference, coverage, referenceLabel, orderedReferences } from './characterLibraryModel.js'

const props = defineProps({ api: { type: Function, required: true } })
const emit = defineEmits(['navigate'])
const versions = ref([])
const reviewStates = ref([])
const showWorkshop = ref(false)
const drafts = ref([])
const workshopCharacter = ref(null)
function reviewState(version) { return reviewStates.value.find(r=>r.versionId===version.id)?.contentStatus || 'NeedReview' }
function age(version) { if(version.payload.facts?.ageSetting)return version.payload.facts.ageSetting;const current=characters.value.find(c=>c.id===version.payload.characterId)?.ageSetting;return current?`当前设定：${current}（旧版未冻结年龄字段）`:'旧版未冻结年龄设定' }
const projects = ref([])
const characters = ref([])
const workflows = ref([])
const history = ref([])
const busy = ref(false)
const error = ref('')
const resolution = ref(null)
const selectedTask = ref(null)
const submittedId = ref(null)
const requestKey = ref(crypto.randomUUID())
const form = reactive({ projectId: null, versionId: null, view: 'front', framing: 'closeUp', seed: 2026102601, prompt: '' })
const versionDialog = ref(false)
const versionBusy = ref(false)
const references = ref([])
const choices = reactive({})
const framingChoices = reactive({})
const capture = reactive({ characterId: null, label: '日常造型', outfit: '', bodyDescription: '', profile: 'baseline480', note: '', requireBasicPack: false })
const galleryVersion = ref(null)
const galleryDialog = ref(false)
const compareVersion = ref(null)
const humanVersion = ref(false)
const versionReviewNote = ref('')
async function reviewVersion(decision) {
  busy.value=true;error.value=''
  try { await props.api(`/api/character-story/versions/${galleryVersion.value.id}/review`,{method:'POST',body:JSON.stringify({decision,humanConfirmed:humanVersion.value,note:versionReviewNote.value,idempotencyKey:crypto.randomUUID()})});humanVersion.value=false;await load() }
  catch(e){error.value=e.message} finally {busy.value=false}
}
const enlargedReference = ref(null)
let disposed = false
let poller
let revision = 0
let detailRevision = 0
let polling = false
const selectedVersion = computed(() => versions.value.find(v => v.id === form.versionId))
const selectedReference = computed(() => selectReference(selectedVersion.value, form.view, form.framing))
const availableViews = computed(() => [...new Set((selectedVersion.value?.payload.references || []).map(r => r.view))])
const availableFramings = computed(() => [...new Set((selectedVersion.value?.payload.references || []).filter(r => r.view === form.view).map(effectiveFraming))])
const selectedTaskContext = computed(() => history.value.find(row => String(row.id) === String(selectedTask.value?.task.id)))
const groups = computed(() => {
  const grouped = new Map()
  for (const version of versions.value) {
    const id = version.payload.characterId
    if (!grouped.has(id)) grouped.set(id, [])
    grouped.get(id).push(version)
  }
  return [...grouped.values()].map(list => ({ id: list[0].payload.characterId, versions: list, latest: list[0] }))
})
const profileWorkflow = computed(() => workflows.value.find(w => w.fileName === (capture.profile === 'quality768' ? 'minimax_h3_local_768_i2v_api.json' : 'minimax_h3_local_i2v_api.json')))
const captureReferences = computed(() => references.value.filter(r => choices[r.id]).map(r => ({ referenceId: r.id, view: choices[r.id], framing: framingChoices[r.id] })))
const captureCoverage = computed(() => coverage(captureReferences.value))
const captureHasDuplicates = computed(() => new Set(captureReferences.value.map(r => referenceKey(r.view, r.framing))).size !== captureReferences.value.length)
const captureCanSave = computed(() => captureReferences.value.length > 0 && captureReferences.value.every(r => captureViews.includes(r.view) && framingNames[r.framing]) && !captureHasDuplicates.value && (!capture.requireBasicPack || captureCoverage.value.complete))
function media(path) { return `/api/media?assetPath=${encodeURIComponent(path)}` }
function historyVersion(id) { return versions.value.find(v => String(v.id) === String(id))?.version || '?' }
function historyFraming(row) { return row.framing || (row.view === 'fullBody' ? 'fullBody' : 'medium') }
function cardVersion(group) { return selectedVersion.value?.payload.characterId === group.id ? selectedVersion.value : group.latest }
function invalidate() { revision++; resolution.value = null; submittedId.value = null; requestKey.value = crypto.randomUUID() }
watch(form, invalidate, { deep: true })
async function load() {
  const responses = await Promise.allSettled([
    props.api('/api/character-library'), props.api('/api/projects'), props.api('/api/characters'),
    props.api('/api/workflows'), props.api('/api/character-library/history'), props.api('/api/character-story/library-reviews'), props.api('/api/character-workshop')
  ])
  if (disposed) return
  const failures = responses.filter(r => r.status === 'rejected').map(r => r.reason.message)
  error.value = failures.join('；')
  if (responses[0].status === 'fulfilled') versions.value = responses[0].value.versions
  if (responses[1].status === 'fulfilled') projects.value = responses[1].value
  if (responses[2].status === 'fulfilled') characters.value = responses[2].value
  if (responses[3].status === 'fulfilled') workflows.value = responses[3].value
  if (responses[4].status === 'fulfilled') history.value = responses[4].value
  if (responses[5].status === 'fulfilled') reviewStates.value = responses[5].value
  if (responses[6].status === 'fulfilled') drafts.value = responses[6].value
  if (!form.projectId && projects.value.length) form.projectId = projects.value[0].id
}
async function resolve() {
  busy.value = true; error.value = ''
  const ticket = revision
  try {
    const result = await props.api('/api/character-library/resolve', { method: 'POST', body: JSON.stringify(form) })
    if (!disposed && ticket === revision) resolution.value = result
  } catch (failure) { if (!disposed && ticket === revision) error.value = failure.message }
  finally { if (!disposed) busy.value = false }
}
async function generate() {
  if (!resolution.value || busy.value || submittedId.value) return
  busy.value = true; error.value = ''
  const ticket = revision
  try {
    const result = await props.api('/api/character-library/generate', { method: 'POST', body: JSON.stringify({ ...form, idempotencyKey: requestKey.value }) })
    if (disposed || ticket !== revision) return
    submittedId.value = result.id
    ElMessage.success(`人物版本已固定，视频任务 #${result.id} 已提交`)
    await selectTask(result.id)
    history.value = await props.api('/api/character-library/history')
  } catch (failure) { if (!disposed && ticket === revision) error.value = failure.message }
  finally { if (!disposed) busy.value = false }
}
async function selectTask(id) {
  const ticket = ++detailRevision
  try {
    const result = await props.api(`/api/tasks/${id}`)
    if (!disposed && ticket === detailRevision) selectedTask.value = result
  } catch (failure) { if (!disposed && ticket === detailRevision) error.value = failure.message }
}
async function poll() {
  if (disposed || polling) return
  polling = true
  try {
    if (selectedTask.value && ['Pending', 'Running'].includes(selectedTask.value.task.status)) await selectTask(selectedTask.value.task.id)
    const latest = await props.api('/api/character-library/history')
    if (!disposed) history.value = latest
  } catch (failure) { if (!disposed) error.value = failure.message }
  finally { polling = false }
}
async function loadReferences() {
  references.value = []; Object.keys(choices).forEach(key => delete choices[key]); Object.keys(framingChoices).forEach(key => delete framingChoices[key])
  const character = characters.value.find(c => c.id === capture.characterId)
  const snapshot = selectedVersion.value?.payload.characterId === capture.characterId ? selectedVersion.value.payload : null
  capture.outfit = snapshot?.outfit || character?.clothes || ''
  capture.bodyDescription = snapshot?.bodyRatio || character?.bodyRatio || ''
  const id = capture.characterId
  if (!id) return
  try {
    const result = await props.api(`/api/characters/${id}/references`)
    if (!disposed && capture.characterId === id) {
      references.value = result.filter(r => r.available && r.reviewStatus !== 'Rejected')
      for (const reference of snapshot?.references || []) {
        choices[reference.referenceId] = captureViews.includes(reference.view) ? reference.view : ''
        framingChoices[reference.referenceId] = effectiveFraming(reference)
      }
    }
  } catch (failure) { error.value = failure.message }
}
async function openCapture() {
  capture.characterId = selectedVersion.value?.payload.characterId || characters.value[0]?.id || null
  capture.label = selectedVersion.value?.payload.label || '日常造型'; capture.profile = selectedVersion.value?.payload.workflow.profile || 'baseline480'; capture.note = ''
  capture.requireBasicPack = selectedVersion.value?.payload.referencePack === 'basic-nine-v1'
  versionDialog.value = true
  await loadReferences()
}
async function saveVersion() {
  if (!capture.characterId || !profileWorkflow.value || !captureCanSave.value) return
  versionBusy.value = true; error.value = ''
  try {
    const body = { label: capture.label, outfit: capture.outfit, bodyDescription: capture.bodyDescription, profile: capture.profile, workflowId: profileWorkflow.value.id, note: capture.note, references: captureReferences.value, referencePack: capture.requireBasicPack ? 'basic-nine-v1' : null, freezeProvenance: true, requireReviewed: true }
    const result = await props.api(`/api/character-library/${capture.characterId}/versions`, { method: 'POST', body: JSON.stringify(body) })
    await load(); form.versionId = result.id; versionDialog.value = false
    ElMessage.success('人物试用版本已保存，旧版本保留')
  } catch (failure) { error.value = failure.message }
  finally { versionBusy.value = false }
}
function manage() { versionDialog.value = false; emit('navigate', 'characters') }
function openGallery(version) { galleryVersion.value = version; compareVersion.value=null;humanVersion.value=false;galleryDialog.value = true }
onMounted(async () => { await load(); if (!disposed) poller = setInterval(poll, 5000) })
onBeforeUnmount(() => { disposed = true; revision++; detailRevision++; clearInterval(poller) })
</script>

<template>
  <section class="page-content character-library-page">
    <div class="toolbar"><div><div class="eyebrow">固定人物 · 跨项目复用</div><h2>人物参考库</h2></div><div class="library-buttons"><el-button @click="showWorkshop=!showWorkshop">人物创建与定型</el-button><el-button @click="emit('navigate','character-story')">剧情选角与关键帧</el-button><el-button @click="manage">管理人物与参考图</el-button><el-button type="primary" @click="openCapture">保存人物版本</el-button></div></div>
    <el-alert title="本库保存人物设定、参考照片和版本记录，不代表已训练专属模型或三维人物。九个槽位齐全与内容合格分别审核。" type="info" :closable="false" />
    <CharacterWorkshopPanel v-if="showWorkshop" :api="api" :initial-character-id="workshopCharacter" @changed="load"/>
    <p class="muted">每套造型按视角和景别保存参考图：3张面部近景＋6张全身为基础参考包。选定人物版本后，再选择镜头需要的角度与景别。</p>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <div class="asset-grid">
      <article v-for="group in groups" :key="group.id" class="library-card character-library-card" :class="{ chosen: selectedVersion?.payload.characterId === group.id }">
        <button class="character-cover" :aria-label="`选择人物 ${group.latest.payload.characterName}`" @click="form.versionId = cardVersion(group).id"><img :src="media(coverReference(cardVersion(group)).assetPath)" :alt="group.latest.payload.characterName" /></button>
        <div class="library-content"><h3>{{ group.latest.payload.characterName }}</h3><p>{{ age(cardVersion(group)) }} · {{ group.latest.payload.faceFeatures || group.latest.payload.hair }}</p>
          <el-select :model-value="cardVersion(group).id" :aria-label="`${group.latest.payload.characterName}的人物版本`" @update:model-value="value => form.versionId = value"><el-option v-for="v in group.versions" :key="v.id" :value="v.id" :label="`v${v.version} · ${v.payload.label}`" /></el-select>
          <div class="coverage-line"><el-tag :type="coverage(cardVersion(group).payload.references).complete ? 'success' : 'info'">基础参考 {{ coverage(cardVersion(group).payload.references).present }}/9</el-tag><span>共 {{ cardVersion(group).payload.references.length }} 张 · {{ reviewState(cardVersion(group))==='Approved'?'已人工审核':reviewState(cardVersion(group))==='Rejected'?'素材拒绝或不可用':'内容待复核' }}</span></div>
          <div class="library-buttons"><el-button size="small" @click="form.versionId = cardVersion(group).id">选择此人物</el-button><el-button size="small" plain :aria-label="`查看${group.latest.payload.characterName}的参考图`" @click="openGallery(cardVersion(group))">查看参考图</el-button></div>
        </div>
      </article>
      <el-empty v-if="!groups.length" description="创建人物并上传参考图后，保存第一个人物版本" />
    </div>
    <template v-if="drafts.length"><h3>候选人物 · 尚未入库</h3><p>以下为真实任务输出的待审候选。用途槽位完整度不代表方向、身份或造型已合格；确认后才能成为项目选角版本。</p><div class="asset-grid"><article v-for="d in drafts.filter(d=>!groups.some(g=>g.id===d.characterId))" :key="d.characterId" class="library-card character-library-card"><button class="character-cover" @click="workshopCharacter=d.characterId;showWorkshop=true"><img v-if="d.cover" :src="media(d.cover)" :alt="d.name+' 待审候选'"/></button><div class="library-content"><h3>{{d.name}} · {{d.ageSetting}}</h3><p>{{d.outfit}}</p><el-tag type="warning">候选 {{d.present}}/9 · 待内容审核 · 未入库</el-tag><p v-if="d.missing.length">缺少：{{d.missing.map(s=>viewNames[s.view]+' '+framingNames[s.framing]).join('、')}}</p><el-button @click="workshopCharacter=d.characterId;showWorkshop=true">检查{{d.name}}候选</el-button></div></article></div></template>
    <div class="two-col">
      <div class="panel"><div class="panel-head"><h3>实验：人物参考图直接试片</h3></div><p>此入口直接用参考照片试片。剧情镜头请进入“剧情选角与关键帧”，先制作并检查场景关键帧。</p>
        <el-alert v-if="selectedVersion&&!selectedReference" :title="`所选版本缺少${viewNames[form.view]||form.view} · ${framingNames[form.framing]||form.framing}参考；请明确调整选择或补图，不会自动替换其他图片。`" type="error" :closable="false"/>
        <el-form label-position="top" :disabled="busy">
          <el-form-item label="人物与版本"><el-select v-model="form.versionId" placeholder="请选择人物版本" aria-label="生成使用的人物版本"><el-option v-for="v in versions" :key="v.id" :value="v.id" :label="`${v.payload.characterName} · v${v.version} · ${v.payload.label}`" /></el-select></el-form-item>
          <el-form-item label="目标项目"><el-select v-model="form.projectId" aria-label="目标项目"><el-option v-for="p in projects" :key="p.id" :value="p.id" :label="p.name" /></el-select></el-form-item>
          <div class="reference-selectors"><el-form-item label="参考视角"><el-select v-model="form.view" :disabled="!selectedVersion" aria-label="参考视角"><el-option v-for="view in availableViews" :key="view" :value="view" :label="viewNames[view] || view" /></el-select></el-form-item><el-form-item label="参考景别"><el-select v-model="form.framing" :disabled="!selectedVersion" aria-label="参考景别"><el-option v-for="framing in availableFramings" :key="framing" :value="framing" :label="framingNames[framing] || framing" /></el-select></el-form-item></div>
          <el-form-item label="这次镜头的人物动作"><el-input v-model="form.prompt" type="textarea" :rows="4" maxlength="4000" show-word-limit placeholder="例如：人物轻轻点头，露出自然微笑，镜头保持固定。" aria-label="镜头动作" /></el-form-item>
          <el-form-item label="种子"><el-input-number v-model="form.seed" :min="0" :max="9007199254740991" aria-label="种子" /></el-form-item>
          <el-button :disabled="!selectedReference || !form.projectId || !form.prompt.trim()" :loading="busy" @click="resolve">预览本次调用</el-button>
        </el-form>
        <div v-if="resolution" class="call-preview" data-testid="library-resolution"><h4>本次固定使用</h4><p>{{ resolution.version.payload.characterName }} · v{{ resolution.version.version }} · {{ resolution.version.payload.label }}</p><p>{{ viewNames[resolution.binding.view] }} · {{ framingNames[resolution.binding.framing || form.framing] }} · {{ resolution.version.payload.workflow.profile === 'quality768' ? '1376×768' : '864×480' }} · 24 FPS · 约5.17秒</p><p class="muted">人物版本 #{{ resolution.version.id }} · 参考图 #{{ resolution.binding.referenceId }}</p><img :src="media(resolution.binding.referenceAssetPath)" alt="本次实际使用的人物参考图" /><details><summary>查看固定设定与镜头描述</summary><p class="prompt-copy">{{ resolution.resolvedPrompt }}</p></details><p class="muted">试用视频生成后仍需检查人物、动作和自然度。</p><el-button type="primary" :disabled="!!submittedId" :loading="busy" @click="generate">{{ submittedId ? `已提交任务 #${submittedId}` : '生成此人物视频' }}</el-button></div>
        <div v-else-if="selectedReference" class="reference-strip"><img :src="media(selectedReference.assetPath)" :alt="referenceLabel(selectedReference)" /><span>{{ referenceLabel(selectedReference) }} · 随人物版本固定保存</span></div>
      </div>
      <div class="panel"><div class="panel-head"><h3>视频结果</h3><el-tag type="warning">内容待复核</el-tag></div>
        <template v-if="selectedTask"><p>任务 #{{ selectedTask.task.id }} · {{ selectedTask.task.status }}</p><p v-if="selectedTaskContext" class="muted">{{ selectedTaskContext.characterName }} · v{{ historyVersion(selectedTaskContext.versionId) }} · {{ viewNames[selectedTaskContext.view] }} · {{ framingNames[historyFraming(selectedTaskContext)] }}</p><el-progress v-if="['Pending', 'Running'].includes(selectedTask.task.status)" :percentage="Math.min(100, Math.floor((selectedTask.task.progress || 0) * 100))" /><p v-if="selectedTask.task.errorMessage" class="library-error">{{ selectedTask.task.errorMessage }}</p><template v-for="result in selectedTask.results || []" :key="result.id"><video v-if="result.available && /\.mp4$/i.test(result.assetPath || '')" controls preload="metadata" :src="result.mediaUrl || media(result.assetPath)" class="library-video" /></template></template>
        <el-empty v-else description="点击下方调用记录可播放已生成的视频" />
      </div>
    </div>
    <div class="panel"><div class="panel-head"><h3>人物库调用记录</h3></div><el-table :data="history" class="dark-table" @row-click="row => selectTask(row.id)"><el-table-column prop="id" label="任务" width="90" /><el-table-column prop="characterName" label="人物" /><el-table-column label="人物版本" width="110"><template #default="{ row }">v{{ historyVersion(row.versionId) }} (#{{ row.versionId }})</template></el-table-column><el-table-column label="视角与景别" min-width="160"><template #default="{ row }">{{ viewNames[row.view] || row.view }} · {{ framingNames[historyFraming(row)] }}</template></el-table-column><el-table-column prop="status" label="执行状态" /><el-table-column prop="createdAt" label="创建时间" min-width="180" /></el-table></div>
    <el-dialog v-model="versionDialog" title="保存人物试用版本" width="720px" :close-on-click-modal="false">
      <p>版本保存后保留原样；修改外貌、造型或参考图时，保存一个新版本。</p><el-form label-position="top" :disabled="versionBusy"><el-form-item label="已有角色"><el-select v-model="capture.characterId" aria-label="入库角色" @change="loadReferences"><el-option v-for="c in characters" :key="c.id" :value="c.id" :label="c.name" /></el-select></el-form-item><el-form-item label="造型名称"><el-input v-model="capture.label" maxlength="100" /></el-form-item><el-form-item label="完整服装与鞋子"><el-input v-model="capture.outfit" type="textarea" :rows="2" maxlength="2000" /></el-form-item><el-form-item label="体型与比例（可选）"><el-input v-model="capture.bodyDescription" type="textarea" :rows="2" maxlength="2000" /></el-form-item><el-form-item label="视频生成规格"><el-select v-model="capture.profile"><el-option value="baseline480" label="480p 试用 · 864×480" /><el-option value="quality768" label="768p 试用 · 1376×768" /></el-select></el-form-item><el-checkbox v-model="capture.requireBasicPack">要求基础9图齐全：3张面部近景＋6张全身</el-checkbox><p class="muted">当前 {{ captureCoverage.present }}/9。分别指定视角和景别；留空的图片不会入库。</p><p v-if="captureHasDuplicates" class="library-error" role="alert">同一视角与景别重复，请为每个组合只保留一张参考图。</p><p v-if="capture.requireBasicPack && !captureCoverage.complete" class="missing-references">待补：{{ captureCoverage.missing.map(([view, framing]) => `${viewNames[view]} · ${framingNames[framing]}`).join('、') }}</p><div v-for="r in references" :key="r.id" class="reference-choice"><img :src="r.mediaUrl || media(r.assetPath)" :alt="`参考图 ${r.id}`" /><div><p>参考图 #{{ r.id }} · {{ r.reviewStatus === 'Approved' ? '已审核' : '待复核' }}</p><el-select v-model="choices[r.id]" clearable :aria-label="`参考图 ${r.id} 的视角`" placeholder="选择参考视角"><el-option v-for="view in captureViews" :key="view" :value="view" :label="viewNames[view]" /></el-select><el-select v-model="framingChoices[r.id]" clearable :aria-label="`参考图 ${r.id} 的景别`" placeholder="选择景别"><el-option v-for="(label, key) in framingNames" :key="key" :value="key" :label="label" /></el-select></div></div><el-empty v-if="!references.length" description="请先在角色管理中上传参考图" /></el-form><template #footer><el-button @click="manage">管理人物与参考图</el-button><el-button type="primary" :loading="versionBusy" :disabled="!profileWorkflow || !captureCanSave" @click="saveVersion">保存新版本</el-button></template>
    </el-dialog>
    <el-dialog v-model="galleryDialog" :title="galleryVersion ? `${galleryVersion.payload.characterName} · v${galleryVersion.version} 参考图` : '人物参考图'" width="min(1100px, 94vw)">
      <template v-if="galleryVersion"><p>{{ galleryVersion.payload.label }} · v{{galleryVersion.version}} · 基础参考 {{ coverage(galleryVersion.payload.references).present }}/9 · {{reviewState(galleryVersion)}}</p><p class="muted">点击原图检查。鼻尖朝画面左/右；前侧不能用纯侧面代替。背面只检查发型、服装、体型，不验证正脸身份。</p><p v-if="!coverage(galleryVersion.payload.references).complete" class="missing-references">待补：{{ coverage(galleryVersion.payload.references).missing.map(([view, framing]) => `${viewNames[view]}${framingNames[framing]}`).join('、') }}</p><div class="reference-gallery"><button v-for="r in orderedReferences(galleryVersion)" :key="r.referenceId" type="button" :aria-label="`放大${referenceLabel(r)}参考图`" @click="enlargedReference = r"><img :src="media(r.assetPath)" :alt="referenceLabel(r)" /><span>{{ referenceLabel(r) }}</span></button></div>
        <el-select v-model="compareVersion" clearable placeholder="选择另一版本比较" aria-label="比较人物版本"><el-option v-for="v in versions.filter(v=>v.payload.characterId===galleryVersion.payload.characterId&&v.id!==galleryVersion.id)" :key="v.id" :value="v.id" :label="'v'+v.version+' · '+v.payload.label"/></el-select><div v-if="compareVersion" class="reference-gallery"><button v-for="r in orderedReferences(versions.find(v=>v.id===compareVersion))" :key="r.referenceId" type="button" @click="enlargedReference=r"><img :src="media(r.assetPath)" :alt="'比较版 '+referenceLabel(r)"/><span>比较版 · {{referenceLabel(r)}}</span></button></div>
        <details><summary>冻结设定、来源任务、参数与审核记录</summary><pre style="white-space:pre-wrap;overflow-wrap:anywhere;max-height:350px;overflow:auto">{{galleryVersion.payload.facts||'旧版未冻结补充来源字段；原版本保持可追溯，不补写历史事实。'}}</pre></details><el-checkbox v-model="humanVersion">我已人工检查所选版本与素材</el-checkbox><el-input v-model="versionReviewNote" type="textarea" placeholder="版本审核结论" aria-label="版本审核结论"/><div class="library-buttons"><el-button :disabled="busy||!humanVersion||!versionReviewNote" @click="reviewVersion('Approved')">批准版本（须逐素材批准）</el-button><el-button :disabled="busy||!humanVersion||!versionReviewNote" type="danger" plain @click="reviewVersion('Rejected')">拒绝版本</el-button></div>
      </template>
    </el-dialog>
    <el-dialog :model-value="!!enlargedReference" :title="enlargedReference ? referenceLabel(enlargedReference) : '参考图'" width="min(1300px, 96vw)" @update:model-value="value => { if (!value) enlargedReference = null }"><img v-if="enlargedReference" class="enlarged-reference" :src="media(enlargedReference.assetPath)" :alt="referenceLabel(enlargedReference)" /></el-dialog>
  </section>
</template>

<style scoped>
.character-library-page { display: grid; gap: 18px; }
.library-buttons { display: flex; flex-wrap: wrap; gap: 8px; }
.character-library-card { display: flex; flex-direction: column; min-width: 0; }
.character-library-card .library-content { width: 100%; }
.character-library-card.chosen { outline: 2px solid #73bdf3; }
.character-cover { width: 100%; height: 210px; padding: 0; border: 0; background: #152033; cursor: pointer; }
.character-cover img { width: 100%; height: 100%; object-fit: cover; }
.character-library-page .el-select { width: 100%; }
.character-library-page .el-input-number { width: 220px; }
.coverage-line { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; margin: 16px 0; font-size: 12px; color: #94a6bf; }
.call-preview { margin-top: 20px; padding-top: 14px; border-top: 1px solid #334155; }
.call-preview img { width: 100%; max-height: 280px; object-fit: contain; background: #111827; border-radius: 8px; }
.call-preview details { margin: 14px 0; }
.prompt-copy { white-space: pre-wrap; overflow-wrap: anywhere; font-size: 13px; line-height: 1.6; }
.library-video { display: block; width: 100%; margin-top: 16px; border-radius: 8px; }
.library-error { color: #ffb4a9; overflow-wrap: anywhere; }
.reference-strip { display: flex; gap: 12px; align-items: center; margin-top: 18px; color: #94a6bf; font-size: 13px; }
.reference-strip img { width: 140px; border-radius: 6px; }
.reference-choice { display: flex; gap: 16px; align-items: center; margin: 16px 0; }
.reference-choice img { width: 150px; height: 85px; object-fit: contain; border-radius: 6px; }
.reference-choice > div { flex: 1; min-width: 0; }
.reference-selectors { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.reference-gallery { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
.reference-gallery button { padding: 0; overflow: hidden; border: 1px solid #42516c; border-radius: 8px; background: #111b2c; color: #e3edfa; cursor: pointer; }
.reference-gallery img { display: block; width: 100%; aspect-ratio: 16/9; object-fit: contain; }
.reference-gallery span { display: block; padding: 10px; text-align: center; }
.enlarged-reference { display: block; width: 100%; max-height: 78vh; object-fit: contain; }
.missing-references { line-height: 1.7; color: #bc9152; }
@media (max-width: 900px) { .character-library-page .two-col, .character-library-page .asset-grid { grid-template-columns: 1fr; } }
</style>
