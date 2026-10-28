"""Read-only Comfy progress events for the studio client; never submits or cancels work."""
import asyncio
import json
from pathlib import Path
import time
import aiohttp

FOLDER = Path(__file__).resolve().parents[3] / 'Data/Qwen3Video20261022'


async def main():
    deadline = time.monotonic() + 14 * 3600
    async with aiohttp.ClientSession(trust_env=False) as session:
        async with session.ws_connect('http://127.0.0.1:8188/ws?clientId=video-studio', heartbeat=20, max_msg_size=16*1024**2) as socket:
            while time.monotonic() < deadline:
                state = json.loads((FOLDER / 'run.json').read_text(encoding='utf-8'))
                if state['stage'] in ['ReadyForUserPreview', 'AwaitingPlaybackInspection', 'Failed', 'Blocked']: break
                # Bound the application wait even when websocket heartbeats keep
                # refreshing aiohttp's internal receive timeout while idle.
                try: message = await asyncio.wait_for(socket.receive(), timeout=10)
                except asyncio.TimeoutError: continue
                if message.type == aiohttp.WSMsgType.TEXT:
                    value = json.loads(message.data)
                    if value.get('type') in ['progress', 'executing', 'execution_start', 'execution_success', 'execution_error']:
                        event = {'epochSeconds': time.time(), 'stage': state['stage'], **value}
                        with (FOLDER / 'comfy-events.jsonl').open('a', encoding='utf-8') as stream: stream.write(json.dumps(event)+'\n')
                        path = FOLDER / 'comfy-progress.json'; temporary = path.with_suffix('.tmp')
                        temporary.write_text(json.dumps(event, indent=2), encoding='utf-8'); temporary.replace(path)
                        print(json.dumps(event), flush=True)
                elif message.type in [aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR]: break


if __name__ == '__main__': asyncio.run(main())
