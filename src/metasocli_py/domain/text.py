"""Source offsets are UTF-16 units; H3 lengths are Unicode scalar values."""
import json
import math
import re

from .errors import AppError


def valid_unicode(text: str) -> str:
    try:
        text.encode('utf-8', errors='strict')
    except UnicodeError:
        raise AppError('INVALID_UNICODE', 'Unpaired Unicode surrogate is forbidden.') from None
    return text


def normalize_text(value: str | bytes) -> str:
    try:
        text = value.decode('utf-8', errors='strict') if isinstance(value, bytes) else value
    except UnicodeError:
        raise AppError('INVALID_UTF8', 'Source must be valid UTF-8.') from None
    valid_unicode(text)
    return text.removeprefix('\ufeff').replace('\r\n', '\n').replace('\r', '\n')


def offset_map(text: str) -> dict[int, int]:
    valid_unicode(text)
    result, offset = {0: 0}, 0
    for index, char in enumerate(text):
        offset += 2 if ord(char) > 0xffff else 1
        result[offset] = index + 1
    return result


def utf16_length(text: str) -> int:
    return len(valid_unicode(text).encode('utf-16-le')) // 2


def utf16_boundary(text: str, offset: int) -> bool:
    return type(offset) is int and offset in offset_map(text)


def utf16_slice(text: str, start: int, end: int) -> str:
    positions = offset_map(text)
    if type(start) is not int or type(end) is not int or start > end or start not in positions or end not in positions:
        raise AppError('UTF16_BOUNDARY', 'Offset is out of range or splits a surrogate pair.')
    return text[positions[start]:positions[end]]


def coverage(text: str, segments: list[dict]) -> None:
    cursor, seen = 0, set()
    for item in segments:
        if item['id'] in seen or item['start'] != cursor or item['end'] <= cursor:
            raise AppError('SOURCE_COVERAGE', 'Segments must cover the source consecutively in order.')
        utf16_slice(text, item['start'], item['end'])
        cursor = item['end']
        seen.add(item['id'])
    if cursor != utf16_length(text):
        raise AppError('SOURCE_COVERAGE', 'Segments omit source text.')


def duration(value: int | float) -> dict:
    if type(value) not in (int, float) or not math.isfinite(value) or not 4 <= math.ceil(value) <= 15:
        raise AppError('DURATION_TARGET', 'Target must round upward into 4–15 seconds.')
    result: dict[str, int | float] = {'duration': math.ceil(value)}
    if value != math.ceil(value):
        result['targetDurationSeconds'] = value
    return result


def validate_narration(segment: dict) -> None:
    narration = segment.get('narration')
    if not narration:
        return
    if any(r['role'] == 'first_frame' for r in segment['references']):
        raise AppError('H3_MODE', 'Narration and first frame are mutually exclusive.')
    previous = 0
    for cue in narration['cues']:
        if cue['start'] < previous or cue['end'] <= cue['start'] or not utf16_slice(segment['prompt'], cue['start'], cue['end']).strip():
            raise AppError('NARRATION_CUE', 'Cues must be ordered nonempty UTF-16 ranges.')
        previous = cue['end']


def narration_direction(segment: dict) -> str:
    validate_narration(segment)
    if not segment.get('narration'):
        return ''
    cues = '\n'.join('- ' + json.dumps(utf16_slice(segment['prompt'], c['start'], c['end']), ensure_ascii=False)
                     for c in segment['narration']['cues'])
    return ('\n\n旁白配音参考（技术适配说明，不改写以上原文）\n'
            '本次输入的参考音频1仅作为画外旁白的音色、咬字、语气、节奏和情绪参考。不得照搬参考音频中的具体台词或剧情，也不是把整条音频铺到整段视频。\n'
            '仅以下原文片段中的叙述性画外旁白使用该声线，按其所在镜头和时间位置演绎；片段列表只用于标注归属，不重复朗读。原文未指定时间时不虚构时码。\n'
            + cues + '\n'
            '人物直接对白仍按对应角色的声线和原文口型要求演绎，不得被旁白音频替代；画外旁白不得驱动无口型人物张嘴。纯对白、环境声、音乐和静默部分不使用旁白声线。完整台词、原有顺序及本段时长保持不变。')


def render_prompt(segment: dict) -> str:
    template = valid_unicode(segment['prompt'])
    if re.search(r'\{\{\s*Node\b', template, re.I):
        raise AppError('LEGACY_REFERENCE', 'Legacy node reference is forbidden.')
    bindings = {r['assetId']: '首帧图片' if r['role'] == 'first_frame' else f'参考图{i+1}'
                for i, r in enumerate(segment['references'])}

    def replace(match: re.Match) -> str:
        if match[1] not in bindings:
            raise AppError('UNKNOWN_REFERENCE', 'Prompt contains an unbound reference.')
        return bindings[match[1]]

    text = re.sub(r'\{\{ref:([^{}]+)\}\}', replace, template) + narration_direction(segment)
    if '{{ref:' in text:
        raise AppError('UNKNOWN_REFERENCE', 'Incomplete reference marker.')
    if not text.strip() or len(text) > 7000:
        raise AppError('PROMPT_LIMIT', 'H3 prompt must contain 1–7000 Unicode code points.')
    return text
