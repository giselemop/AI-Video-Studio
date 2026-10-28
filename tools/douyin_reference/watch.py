"""Read-only Comfy progress observer. Never submits or cancels inference."""
import asyncio
import json
from pathlib import Path
import time
import aiohttp

FOLDER=Path(__file__).resolve().parents[3]/'Data/DouyinReference20261023'


async def main():
    async with aiohttp.ClientSession(trust_env=False) as session:
        async with session.ws_connect('http://127.0.0.1:8188/ws?clientId=video-studio',heartbeat=20,max_msg_size=16*1024**2) as socket:
            deadline=time.monotonic()+12*3600
            while time.monotonic()<deadline:
                state=json.loads((FOLDER/'run.json').read_text(encoding='utf-8'))
                if state['stage'] in ['ReadyForUserPreview','AwaitingPlaybackInspection','Failed','Blocked']:break
                try:message=await asyncio.wait_for(socket.receive(),timeout=10)
                except asyncio.TimeoutError:continue
                if message.type==aiohttp.WSMsgType.TEXT:
                    value=json.loads(message.data)
                    if value.get('type') not in ['progress','executing','execution_start','execution_success','execution_error']:continue
                    event={'epochSeconds':time.time(),'stage':state['stage'],**value}
                    with (FOLDER/'comfy-events.jsonl').open('a',encoding='utf-8') as stream:stream.write(json.dumps(event)+'\n')
                    temporary=FOLDER/'comfy-progress.tmp'
                    temporary.write_text(json.dumps(event,indent=2),encoding='utf-8');temporary.replace(FOLDER/'comfy-progress.json')
                    print(json.dumps(event),flush=True)
                elif message.type in [aiohttp.WSMsgType.CLOSED,aiohttp.WSMsgType.ERROR]:break


if __name__=='__main__':asyncio.run(main())
