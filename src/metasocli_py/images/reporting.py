"""Offline image index and video readiness; never creates a video plan or task."""
import json
from pathlib import Path

from ..application.story import STATE, load_story
from ..domain.errors import AppError
from ..persistence.codec import digest, sealed
from ..persistence.files import atomic_write, project_path, write_json
from ..video.planning import build_request, capture, now, validate_source


def write_reports(root: Path, plan: dict, result: dict) -> None:
    story = load_story(root)
    index = f'{STATE}/image-runs/{plan["planId"]}-index.md'
    lines = ['# Image results', '', f'Plan: {plan["planId"]}', '', 'Provider capacity is not independently verified.', '']
    for row in result['items']:
        asset = next(a for a in story['assets'] if a['recipe']['assetId'] == row['assetId'])
        lines.append(f'- {row["assetId"]}: {row["status"]}; operation: {row.get("operationId", "none")}')
        media = row.get('result') or (asset['media'] if row['status'] == 'reused' else None)
        if media:
            lines.append(f'  ![{row["assetId"]}](../../{media["path"]})')
    atomic_write(project_path(root, index), ('\n'.join(lines)+'\n').encode('utf-8'))
    result['indexPath'] = index
    if result['complete']:
        segments = []
        for eid, sid in plan['scope']:
            row = {'episodeId': eid, 'segmentId': sid}
            try:
                validate_source(root, next(e for e in story['episodes'] if e['id'] == eid))
                request = build_request(root, capture(story, eid, sid))
                row.update(ok=True, requestHash=digest(request), requestBytes=len(json.dumps(request, ensure_ascii=False).encode('utf-8')))
            except AppError as error:
                row.update(ok=False, error={'code': error.code, 'message': error.message})
            segments.append(row)
        check = {'planId': plan['planId'], 'planHash': plan['planHash'], 'checkedAt': now(), 'revision': story['revision'],
                 'ok': all(s['ok'] for s in segments), 'segments': segments, 'videoRequiresSeparateConfirmation': True}
        write_json(project_path(root, f'{STATE}/image-runs/{plan["planId"]}-video-check.json'), sealed(check))
        result['videoCheck'] = check
