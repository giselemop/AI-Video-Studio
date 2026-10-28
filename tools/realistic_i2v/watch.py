"""Observe Comfy progress for the local run; never submit, cancel or modify jobs."""
import asyncio
import json
from pathlib import Path
import time
import aiohttp

FOLDER=Path(__file__).resolve().parents[3]/'Data/RealisticI2V20261022'


async def main():
    deadline=time.monotonic()+18*3600
    async with aiohttp.ClientSession(trust_env=False) as session:
        async with session.ws_connect('http://127.0.0.1:8188/ws?clientId=video-studio',heartbeat=20,max_msg_size=16*1024**2) as socket:
            while time.monotonic()<deadline:
                state=json.loads((FOLDER/'run.json').read_text(encoding='utf-8'))
                if state['stage'] in ['ReadyForUserPreview','AwaitingPlaybackInspection','Failed','Blocked']:break
                try:message=await asyncio.wait_for(socket.receive(),timeout=10)
                except asyncio.TimeoutError:continue
                if message.type==aiohttp.WSMsgType.TEXT:
                    value=json.loads(message.data)
                    if value.get('type') in ['progress','executing','execution_start','execution_success','execution_error']:
                        event={'epochSeconds':time.time(),'stage':state['stage'],**value}
                        with (FOLDER/'comfy-events.jsonl').open('a',encoding='utf-8') as stream:stream.write(json.dumps(event)+'\n')
                        temporary=FOLDER/'comfy-progress.tmp'
                        temporary.write_text(json.dumps(event,indent=2),encoding='utf-8');temporary.replace(FOLDER/'comfy-progress.json')
                        print(json.dumps(event),flush=True)
                elif message.type in [aiohttp.WSMsgType.CLOSED,aiohttp.WSMsgType.ERROR]:break


if __name__=='__main__':asyncio.run(main())
