<script setup>
import { ref,reactive,computed,watch } from 'vue'
import { defaultRegions,regionIssues,sceneWorkflow,maskedSceneWorkflow } from './characterSceneModel.js'
const props=defineProps({api:Function,projectId:Number,versions:{type:Array,default:()=>[]},disabled:Boolean})
const emit=defineEmits(['refresh','busy-change'])
const scenes=ref([]),sceneId=ref(0),viewId=ref(null),source=ref(null),zoom=ref(null),busy=ref(false),error=ref(''),regions=ref(defaultRegions())
const form=reactive({name:'',description:'',sourceTaskId:null,workflowVersion:sceneWorkflow})
const viewed=computed(()=>props.versions.find(v=>v.id===viewId.value)),selected=computed(()=>scenes.value.find(s=>s.id===sceneId.value)),issues=computed(()=>regionIssues(regions.value))
const media=p=>'/api/media?assetPath='+encodeURIComponent(p)
const post=(url,body)=>props.api(url,{method:'POST',body:JSON.stringify(body)})
let generation=0
watch(()=>props.projectId,async id=>{const current=++generation;scenes.value=[];sceneId.value=0;viewId.value=null;source.value=null;error.value='';regions.value=defaultRegions();Object.assign(form,{name:'',description:'',sourceTaskId:null,workflowVersion:sceneWorkflow});if(!id)return;try{const rows=await props.api('/api/scenes?projectId='+id);if(current===generation)scenes.value=rows}catch(e){if(current===generation)error.value=e.message}},{immediate:true})
watch(()=>props.versions,rows=>{if(!rows.some(v=>v.id===viewId.value))viewId.value=rows[0]?.id??null})
watch(()=>form.sourceTaskId,()=>{source.value=null})
watch(sceneId,()=>{if(selected.value){form.name=selected.value.name;form.description=selected.value.fixedPrompt||selected.value.description||''}})
async function act(fn){if(busy.value||props.disabled)return;busy.value=true;emit('busy-change',true);error.value='';try{await fn()}catch(e){error.value=e.message}finally{busy.value=false;emit('busy-change',false)}}
async function loadSource(){await act(async()=>{source.value=null;if(!form.sourceTaskId)throw Error('填写已检查的剧情关键帧任务ID');const d=await props.api('/api/tasks/'+form.sourceTaskId);const png=d.results.find(r=>r.available&&r.assetPath?.endsWith('.png'));if(d.task.status!=='Succeeded'||d.task.taskType!=='Keyframe'||!png||png.width!==1536||png.height!==864)throw Error('来源须为真实成功的1536×864剧情关键帧；请检查文件与尺寸');source.value={...png,taskId:d.task.id}})}
async function capture(){await act(async()=>{
  if(!source.value||source.value.taskId!==form.sourceTaskId)throw Error('先读取并查看实际来源关键帧')
  if(issues.value.length)throw Error(issues.value.join('；'))
  if(!form.description.trim())throw Error('填写固定场景说明')
  if(selected.value&&selected.value.anchorPath!==source.value.assetPath)throw Error('现有场景锚点与来源图不同；请另建场景，不覆盖旧锚点')
  if(!sceneId.value){if(!form.name.trim())throw Error('填写新场景名称');const r=await post('/api/scenes',{projectId:props.projectId,name:form.name,description:form.description,fixedPrompt:form.description,anchorPath:source.value.assetPath,style:'Photorealistic fixed-camera medium two-shot'});scenes.value=await props.api('/api/scenes?projectId='+props.projectId);sceneId.value=r.id}
  const result=await post(`/api/character-story/scenes/${sceneId.value}/capture`,{sourceTaskId:source.value.taskId,description:form.description,regions:regions.value,workflowVersion:form.workflowVersion,idempotencyKey:crypto.randomUUID()})
  viewId.value=result.id;emit('refresh')
})}
const box=r=>({left:r.x/1536*100+'%',top:r.y/864*100+'%',width:r.width/1536*100+'%',height:r.height/864*100+'%'})
</script>
<template><section class="panel scene-panel">
  <h2>固定场景与机位版本</h2><p>把已检查的双人关键帧保存为构图基准。人物、造型、画面左右站位和机位一起冻结；换演员或机位须明确新建基准。含人物的原图不是空场景。</p>
  <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon/>
  <div v-if="versions.length" class="controls"><el-select v-model="viewId" aria-label="查看场景版本" :disabled="busy||disabled"><el-option v-for="v in versions" :key="v.id" :value="v.id" :label="`${v.payload.sceneName} · v${v.version} (#${v.id})`"/></el-select></div>
  <template v-if="viewed"><p class="hash">版本 #{{viewed.id}} · SHA256 {{viewed.sha256}}<br>来源任务 #{{viewed.payload.source.taskId}} · {{viewed.payload.source.reviewScope}} · 内容 NeedReview / 发布 Blocked</p><p>固定演员：{{viewed.payload.actorVersions.map(a=>'人物 #'+a.characterId+' / 版本 #'+a.versionId+' / 画面'+(a.position==='left'?'左':'右')).join('；')}}</p>
  <div class="scene-image"><img :src="media(viewed.payload.source.path)" alt="冻结的场景构图基准" @click="zoom=viewed.payload.source.path"/><span v-for="r in viewed.payload.regions" :key="r.side" class="region" :style="box(r)"><b>{{r.side==='left'?'画面左人物区':'画面右人物区'}}</b></span></div>
  <p>方框外使用原场景像素；框内由Klein生成并羽化合成，接缝和人物仍需目检。{{viewed.payload.workflowVersion===maskedSceneWorkflow?'该版本隔离条件图旧头部姿态，真实生成效果尚未验证。':'原始五输入路线已有真实输出，方向与手部可能失败。'}}</p>
  <details><summary>查看冻结来源、区域与调用记录</summary><pre>{{viewed}}</pre></details></template>
  <details class="capture"><summary>从实际关键帧新建场景版本（不提交GPU任务）</summary>
  <div class="controls"><el-select v-model="sceneId" aria-label="场景归属" :disabled="busy||disabled"><el-option :value="0" label="另建新场景"/><el-option v-for="s in scenes" :key="s.id" :value="s.id" :label="s.name+' (#'+s.id+')'"/></el-select><el-input v-model="form.name" aria-label="场景版本名称" placeholder="场景名称" :disabled="busy||disabled||!!sceneId"/><el-input v-model.number="form.sourceTaskId" type="number" min="1" step="1" aria-label="场景来源任务ID" :disabled="busy||disabled"/><el-button @click="loadSource" :disabled="busy||disabled">读取来源图</el-button></div>
  <img v-if="source" class="source" :src="media(source.assetPath)" alt="待冻结的真实场景来源" @click="zoom=source.assetPath"/>
  <el-input v-model="form.description" type="textarea" aria-label="固定场景说明" placeholder="描述固定书架、背景、光线和布局" :disabled="busy||disabled"/>
  <p>坐标以1536×864画布为准。左右按观众看到的画面方向；区域须覆盖完整的人物、手和可能的轻微运动，不能重叠。</p>
  <div v-for="r in regions" :key="r.side" class="region-form"><strong>{{r.side==='left'?'画面左':'画面右'}}</strong><label v-for="[key,label] in [['x','X'],['y','Y'],['width','宽'],['height','高'],['feather','羽化']]" :key="key">{{label}}<el-input v-model.number="r[key]" type="number" step="1" :aria-label="(r.side==='left'?'左人物区':'右人物区')+label" min="0" :max="key==='feather'?64:1536" :disabled="busy||disabled"/></label></div>
  <el-alert v-for="issue in issues" :key="issue" :title="issue" type="warning" :closable="false"/>
  <div class="controls"><el-select v-model="form.workflowVersion" aria-label="场景工作流路线" :disabled="busy||disabled"><el-option :value="sceneWorkflow" label="原始五输入路线（已运行，内容待审）"/><el-option :value="maskedSceneWorkflow" label="隔离旧头部姿态路线（真实效果未验证）"/></el-select><el-button type="primary" :disabled="busy||disabled||!source||issues.length>0" @click="capture">保存新的场景构图版本</el-button></div><p>保存时服务端重新检查原图哈希、尺寸、来源任务和试片检查。保存仅冻结版本，内容仍待人工审核，不自动批准或生成视频。</p>
  </details><el-dialog :model-value="!!zoom" title="场景基准原图" width="96%" @update:model-value="v=>{if(!v)zoom=null}"><img v-if="zoom" class="source" :src="media(zoom)" alt="场景基准原图放大"/></el-dialog>
</section></template>
<style scoped>.scene-panel{padding:20px;min-width:0}.controls,.region-form{display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin:14px 0}.controls .el-select,.controls .el-input{width:330px}.scene-image{position:relative;max-width:1100px}.scene-image img,.source{display:block;width:100%;object-fit:contain;cursor:zoom-in}.source{max-height:78vh}.region{position:absolute;border:2px solid #67d8d0;pointer-events:none}.region:last-child{border-color:#e4b75c}.region b{background:#152333d9;padding:3px;color:white;font-size:12px}.region-form label{display:grid;gap:5px;font-size:13px}.region-form .el-input{width:120px}.hash,pre{overflow-wrap:anywhere}pre{white-space:pre-wrap;max-height:380px;overflow:auto}summary{cursor:pointer}.capture{margin-top:20px;padding-top:14px;border-top:1px solid #566276}</style>
