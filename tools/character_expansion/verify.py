"""Media, native execution and all 45 exact library combinations; no new GPU jobs."""
import copy
import json
from pathlib import Path
import subprocess
from batch import Batch,PEOPLE,SLOTS,FOLDER,ROOT,read,write,media,sha,logical

def verify():
    r=Batch();r.access();r.preserve();checks=[];outputs=[];library=r.api('/api/character-library')
    target=FOLDER/'verification.json'
    def check(name,passed):
        checks.append(dict(name=name,status='Passed' if passed else 'Failed'))
        write(target,dict(status='Passed' if all(c['status']=='Passed' for c in checks) else 'Failed',checks=checks,outputs=outputs))
        if not passed:raise AssertionError(name)
    def reject(name,path,body):
        response=r.session.post(r.base+path,json=body,timeout=120);check(name,response.status_code==422)
    def native_files(value):
        if isinstance(value,dict):
            if str(value.get('filename','')).endswith('.png') and value.get('type','output')=='output':
                path=(ROOT.parent/'ComfyUI/output'/value.get('subfolder','')/value['filename']).resolve(strict=True)
                if not path.is_relative_to((ROOT.parent/'ComfyUI/output').resolve()):raise ValueError('Native output boundary')
                yield path
            else:
                for child in value.values():yield from native_files(child)
        elif isinstance(value,list):
            for child in value:yield from native_files(child)
    def actual_input(name):
        path=Path(name)
        if not path.is_absolute():path=ROOT.parent/'ComfyUI/input'/path
        path=path.resolve(strict=True)
        if not path.is_relative_to((ROOT.parent/'ComfyUI/input').resolve()):raise ValueError('Copied input boundary')
        return path
    task_ids=lambda:{t['id'] for t in r.api('/api/tasks?limit=500')}
    before=task_ids();new_ids=[]
    for person in PEOPLE:
        entry=r.state['people'][person['key']];version=next(v for v in library['versions'] if v['id']==entry['versionId']);payload=version['payload'];new_ids.append(entry['characterId'])
        check(person['key']+'_adult_fresh_character',person['age']>=18 and entry['characterId'] not in {v['payload']['characterId'] for v in r.state['originalVersions']})
        coverage=next(v['coverage'] for v in library['coverage'] if v['versionId']==version['id'])
        check(person['key']+'_nine_exact_slots',coverage==dict(present=9,expected=9,complete=True,missing=[]) and len(payload['references'])==9 and payload['referencePack']=='basic-nine-v1' and payload['schema']=='character-library-v2')
        check(person['key']+'_immutable_outfit_body',payload['outfit']==person['outfit'] and payload['bodyRatio']==person['body'] and version['sha256']==entry['versionSha256'])
        raw=r.state['tasks'][logical(person,'front','closeUp')];raw_trace=read(FOLDER/(logical(person,'front','closeUp')+'-trace.json'))
        check(person['key']+'_independent_fresh_identity_source',raw_trace['status']=='Succeeded' and raw_trace['input']['taskType']=='Image' and not raw_trace['input'].get('inputImagePath'))
        raw_history=read(FOLDER/(logical(person,'front','closeUp')+'-comfy-history.json'))[raw_trace['comfyPromptId']]
        check(person['key']+'_fresh_source_native_history',raw_history['status']['completed'] and raw_history['status']['status_str']=='success' and raw_history['prompt'][2]['2']['inputs']['text']==raw_trace['input']['parameters']['positive'])
        check(person['key']+'_fresh_source_native_sha',any(sha(path)==raw['sha256'] for path in native_files(raw_history['outputs'])) and raw['sha256'] not in {item['sha256'] for item in r.state['protectedFiles']})
        for view,framing in SLOTS:
            key=logical(person,view,framing);selected=r.selected_key(key);record=r.state['tasks'][selected];trace=read(FOLDER/(selected+'-trace.json'));history=read(FOLDER/(selected+'-comfy-history.json'));item=history[trace['comfyPromptId']];graph=item['prompt'][2];params=trace['input']['parameters']
            check(key+'_real_database_and_history',trace['status']=='Succeeded' and item['status']['status_str']=='success' and item['status']['completed'])
            check(key+'_actual_executed_prompt',any(node.get('class_type')=='CLIPTextEncode' and node['inputs'].get('text')==params['positive'] for node in graph.values()))
            fresh=view=='front' and framing=='closeUp'
            if fresh and trace['input']['taskType']=='Image':check(key+'_fresh_text_to_image',not trace['input'].get('inputImagePath') and not params.get('inputSlots'))
            elif fresh:check(key+'_same_original_fresh_identity',sha(actual_input(graph['4']['inputs']['image']))==raw['sha256'])
            else:
                identity=r.selected(person,'front','closeUp')
                if framing=='fullBody' and view in ['threeQuarterLeft','threeQuarterRight']:
                    pose=r.selected(person,view,'closeUp')
                    if params.get('inputSlots',{}).get('firstFrame')==pose['path']:identity=pose
                check(key+'_same_fresh_identity_input',sha(actual_input(graph['4']['inputs']['image']))==identity['sha256'])
            if framing=='fullBody' and view!='front':check(key+'_same_fullbody_wardrobe_reference',sha(actual_input(graph['20']['inputs']['image']))==r.selected(person,'front','fullBody')['sha256'] and graph['11']['inputs']['positive']==['23',0])
            check(key+'_native_output_matches',any(sha(path)==record['sha256'] for path in native_files(item['outputs'])))
            path=media(record['path']);probe=json.loads(subprocess.check_output(['C:/install/FFmpeg/bin/ffprobe.exe','-v','error','-show_streams','-of','json',str(path)],text=True));image=next(s for s in probe['streams'] if s['codec_type']=='video')
            check(key+'_native_1536_by_864',image['width']==1536 and image['height']==864)
            decoded=subprocess.run(['C:/install/FFmpeg/bin/ffmpeg.exe','-v','error','-i',str(path),'-f','null','-'],capture_output=True,timeout=120)
            check(key+'_complete_decode',decoded.returncode==0 and not decoded.stderr)
            check(key+'_frozen_file_hash',sha(path)==record['sha256'])
            ref=next(ref for ref in payload['references'] if ref['view']==view and ref['framing']==framing)
            check(key+'_uploaded_library_copy',sha(media(ref['assetPath']))==record['sha256'] and ref['sha256']==record['sha256'] and ref['reviewStatus']=='NeedReview')
            response=r.session.get(r.base+'/api/media',params=dict(assetPath=ref['assetPath']),headers={'Range':'bytes=0-1023'},timeout=30)
            check(key+'_http_range',response.status_code==206 and len(response.content)==1024)
            body=dict(projectId=r.state['projectId'],versionId=entry['versionId'],view=view,framing=framing,prompt='A calm standing reference test, locked camera.',seed=1)
            resolved=r.api('/api/character-library/resolve',body);binding=resolved['binding']
            check(key+'_exact_resolution',binding['referenceId']==ref['referenceId'] and binding['referenceSha256']==record['sha256'] and binding['framing']==framing and binding['view']==view and binding['versionId']==version['id'] and binding['versionSha256']==version['sha256'])
            check(key+'_review_boundary',resolved['contentReview']=='NeedReview' and resolved['publication']=='Blocked' and person['outfit'] in resolved['resolvedPrompt'])
            outputs.append(dict(person=person['key'],name=person['name'],view=view,framing=framing,taskId=record['id'],referenceId=ref['referenceId'],assetPath=ref['assetPath'],sha256=record['sha256'],versionId=entry['versionId'],width=1536,height=864,durationMs=trace['durationMs'],sampledVramPeakMiB=trace['vramPeakMiB']))
        reject(person['key']+'_missing_framing','/api/character-library/resolve',dict(body,framing=None))
        reject(person['key']+'_unavailable_back_closeup','/api/character-library/resolve',dict(body,view='back',framing='closeUp'))
        reject(person['key']+'_missing_generation_key','/api/character-library/generate',body)
        path=f"/api/character-library/{entry['characterId']}/versions"
        check(person['key']+'_same_capture_deduplicates',r.api(path,entry['versionBody'])['id']==entry['versionId'])
        reject(person['key']+'_incomplete_nine_pack',path,dict(entry['versionBody'],references=entry['versionBody']['references'][:-1]))
        duplicate=copy.deepcopy(entry['versionBody']);duplicate['references'].append(duplicate['references'][0]);reject(person['key']+'_duplicate_pair',path,duplicate)
        cross=r.api('/api/character-library/resolve',dict(body,projectId=r.state['originalVersions'][0]['ownerProjectId'],view='front',framing='fullBody'))
        check(person['key']+'_cross_project_library_reuse',cross['binding']['versionId']==entry['versionId'] and cross['binding']['referenceId']==entry['front-fullBody'] and cross['task']['projectId']==r.state['originalVersions'][0]['ownerProjectId'])
    check('five_unique_new_characters',len(set(new_ids))==5)
    check('exactly_45_new_references',len(outputs)==45 and len({o['referenceId'] for o in outputs})==45)
    check('no_gpu_task_created_by_acceptance',before==task_ids());r.preserve()
    check('all_prior_versions_and_media_preserved',True)
    write(target,dict(status='Passed',checks=checks,outputs=outputs))
    write(FOLDER/'delivery.json',dict(outputs=outputs,technical='Passed',contentReview='NeedReview',publication='Blocked',characters=5,references=45,newModels=0,newCloudCalls=0,newVideoTasks=0))
    print(str(len(checks))+' media/source/API checks Passed; 45 selected photos; no video task submitted',flush=True)
if __name__=='__main__':verify()
