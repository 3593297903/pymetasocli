import asyncio
import json
import os
import subprocess
import tempfile
from pathlib import Path

from .inspect import video_info


def verify_av(path: Path, expected_hash: str) -> dict:
    try:
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            probe = subprocess.run(['ffprobe', '-v', 'error', '-protocol_whitelist', 'file,pipe', '-f', 'mov',
                '-show_entries', 'stream=codec_type', '-of', 'json', str(path)], stdout=stdout, stderr=stderr, timeout=120, creationflags=flags)
            stdout.seek(0)
            content = stdout.read(256*1024+1)
            if probe.returncode or len(content) > 256*1024:
                return {'passed': False, 'reason': 'AV_VERIFICATION_FAILED'}
            streams = [s.get('codec_type') for s in json.loads(content).get('streams', [])]
            if 'video' not in streams or 'audio' not in streams:
                return {'passed': False, 'reason': 'AV_STREAM_MISSING'}
            decoded = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-protocol_whitelist', 'file,pipe', '-f', 'mov',
                '-i', str(path), '-map', '0:v', '-map', '0:a', '-f', 'null', '-'], stdout=stdout, stderr=stderr, timeout=120, creationflags=flags)
            if decoded.returncode:
                return {'passed': False, 'reason': 'AV_VERIFICATION_FAILED'}
            if video_info(path)['sha256'] != expected_hash:
                return {'passed': False, 'reason': 'OUTPUT_CHANGED'}
            return {'passed': True}
    except FileNotFoundError:
        return {'passed': False, 'reason': 'AV_TOOL_UNAVAILABLE'}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {'passed': False, 'reason': 'AV_VERIFICATION_FAILED'}


async def verify_delivery(root: Path, delivery: dict) -> dict:
    from ..persistence.files import project_path
    for row in delivery['segments']:
        if row.get('output'):
            row['av'] = await asyncio.to_thread(verify_av, project_path(root, row['output']['path']), row['output']['sha256'])
    if any(row.get('av', {}).get('passed') is False for row in delivery['segments']):
        delivery['phase'] = 'delivery_incomplete'
    return delivery
