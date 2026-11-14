import hashlib
import io
import math
import os
import struct
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from ..domain.errors import AppError
from ..persistence.files import identity, safe_path

MAX_IMAGE = 30 * 1024 * 1024
MAX_AUDIO = 15 * 1024 * 1024
MAX_VIDEO = 512 * 1024 * 1024


def image_info(data: bytes) -> dict:
    if not 0 < len(data) <= MAX_IMAGE:
        raise AppError('IMAGE_LIMIT', 'Image exceeds 30 MiB.')
    try:
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
            mime = {'PNG': 'image/png', 'JPEG': 'image/jpeg', 'WEBP': 'image/webp'}.get(image.format or '')
            if not mime or getattr(image, 'n_frames', 1) != 1:
                raise AppError('IMAGE_INVALID', 'Expected a single-frame PNG/JPEG/WebP.')
            if not 256 <= width <= 5760 or not 256 <= height <= 5760 or not .4 <= width / height <= 2.5:
                raise AppError('IMAGE_DIMENSIONS', 'Dimensions must be 256–5760 and ratio 0.4–2.5.')
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            image.load()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise AppError('IMAGE_INVALID', 'Invalid or truncated image.') from None
    return {'mime': mime, 'width': width, 'height': height}


def audio_info(data: bytes) -> dict:
    if not 0 < len(data) <= MAX_AUDIO:
        raise AppError('AUDIO_LIMIT', 'Audio exceeds 15 MiB.')
    try:
        result = wave_info(data) if data[:4] == b'RIFF' else mp3_info(data)
    except (IndexError, struct.error, ZeroDivisionError):
        raise AppError('AUDIO_INVALID', 'Truncated audio metadata.') from None
    if not 2 <= result['duration'] <= 15:
        raise AppError('AUDIO_DURATION', 'Reference audio must be 2–15 seconds.')
    return result


def wave_info(b: bytes) -> dict:
    def invalid():
        raise AppError('AUDIO_INVALID', 'WAV container or sample metadata is invalid.')
    if len(b) < 44 or b[8:12] != b'WAVE' or int.from_bytes(b[4:8], 'little') + 8 != len(b):
        invalid()
    offset, align, rate, channels, size_data = 12, 0, 0, 0, 0
    format_seen = data_seen = False
    while offset + 8 <= len(b):
        name, size = b[offset:offset+4], int.from_bytes(b[offset+4:offset+8], 'little')
        start = offset + 8
        if start + size > len(b):
            invalid()
        if name == b'fmt ':
            if format_seen or size < 16:
                invalid()
            format_seen = True
            fmt, channels, rate, byte_rate, align, bits = struct.unpack_from('<HHIIHH', b, start)
            if fmt == 0xfffe:
                if size < 40 or b[start+26:start+40] != bytes.fromhex('000000001000800000aa00389b71'):
                    invalid()
                fmt = int.from_bytes(b[start+24:start+26], 'little')
            if fmt not in (1, 3) or bits not in ((8, 16, 24, 32) if fmt == 1 else (32, 64)):
                invalid()
            if channels not in (1, 2) or not 8000 <= rate <= 192000 or align != channels * bits // 8 or byte_rate != rate * align:
                invalid()
        elif name == b'data':
            if data_seen:
                invalid()
            data_seen, size_data = True, size
        offset = start + size + size % 2
    if offset != len(b) or not format_seen or not data_seen or not size_data or size_data % align:
        invalid()
    return {'mime': 'audio/wav', 'duration': size_data / align / rate, 'sampleRate': rate, 'channels': channels}


def mp3_info(b: bytes) -> dict:
    def invalid():
        raise AppError('AUDIO_INVALID', 'Expected complete consistent MPEG Layer III frames.')
    offset, end = 0, len(b)
    if b[:3] == b'ID3':
        if len(b) < 10 or b[3] not in (2, 3, 4) or any(n > 127 for n in b[6:10]):
            invalid()
        offset = 10 + sum(n << shift for n, shift in zip(b[6:10], (21, 14, 7, 0), strict=True))
        if b[3] == 4 and b[5] & 16:
            offset += 10
    if b[-128:-125] == b'TAG':
        end -= 128
    frames = samples = rate = channels = 0
    declared = None
    while offset + 4 <= end:
        h = int.from_bytes(b[offset:offset+4], 'big')
        version, layer, bitrate_index, rate_index = h >> 19 & 3, h >> 17 & 3, h >> 12 & 15, h >> 10 & 3
        if h >> 21 != 0x7ff or version == 1 or layer != 1 or bitrate_index in (0, 15) or rate_index == 3:
            invalid()
        current_rate = (44100, 48000, 32000)[rate_index] // (1 if version == 3 else 2 if version == 2 else 4)
        count = 1 if h >> 6 & 3 == 3 else 2
        rates = (0,32,40,48,56,64,80,96,112,128,160,192,224,256,320) if version == 3 else (0,8,16,24,32,40,48,56,64,80,96,112,128,144,160)
        length = (144 if version == 3 else 72) * rates[bitrate_index] * 1000 // current_rate + (h >> 9 & 1)
        if offset + length > end or length < 24 or (frames and (rate != current_rate or channels != count)):
            invalid()
        if not frames:
            side = (17 if count == 1 else 32) if version == 3 else (9 if count == 1 else 17)
            xing = offset + 4 + (0 if h >> 16 & 1 else 2) + side
            if xing + 12 <= offset + length and b[xing:xing+4] in (b'Xing', b'Info') and int.from_bytes(b[xing+4:xing+8], 'big') & 1:
                declared = int.from_bytes(b[xing+8:xing+12], 'big')
        rate, channels = current_rate, count
        frames += 1
        samples += 1152 if version == 3 else 576
        offset += length
    if offset != end or frames < 2 or not rate or (declared is not None and declared not in (frames, frames-1)):
        invalid()
    if declared is not None:
        samples = samples // frames * declared
    return {'mime': 'audio/mpeg', 'duration': samples / rate, 'sampleRate': rate, 'channels': channels}


def boxes(data: bytes):
    offset = 0
    while offset < len(data):
        if offset + 8 > len(data):
            raise AppError('VIDEO_INVALID', 'Truncated MP4 box.')
        size, kind = struct.unpack_from('>I4s', data, offset)
        header = 8
        if size == 1:
            if offset + 16 > len(data):
                raise AppError('VIDEO_INVALID', 'Truncated extended MP4 box.')
            size, header = int.from_bytes(data[offset+8:offset+16], 'big'), 16
        if size == 0:
            size = len(data) - offset
        if size < header or offset + size > len(data):
            raise AppError('VIDEO_INVALID', 'Invalid MP4 box bounds.')
        yield kind, data[offset+header:offset+size]
        offset += size


def video_info(path: Path) -> dict:
    path = safe_path(path)
    with path.open('rb') as stream:
        before = os.fstat(stream.fileno())
        if not 32 <= before.st_size <= MAX_VIDEO:
            raise AppError('VIDEO_INVALID', 'Invalid video size.')
        h = hashlib.sha256()
        while chunk := stream.read(65536):
            h.update(chunk)
        stream.seek(0)
        ftyp = mdat = False
        moov = None
        while stream.tell() < before.st_size:
            start = stream.tell()
            header = stream.read(8)
            if len(header) != 8:
                raise AppError('VIDEO_INVALID', 'Truncated MP4 header.')
            size, kind = struct.unpack('>I4s', header)
            count = 8
            if size == 1:
                extra = stream.read(8)
                if len(extra) != 8:
                    raise AppError('VIDEO_INVALID', 'Truncated MP4 extended header.')
                size, count = int.from_bytes(extra, 'big'), 16
            if size == 0:
                size = before.st_size - start
            if size < count or start + size > before.st_size:
                raise AppError('VIDEO_INVALID', 'Invalid MP4 bounds.')
            if kind == b'ftyp':
                ftyp = size >= 16
            if kind == b'mdat':
                mdat = size > count
            if kind == b'moov':
                if moov is not None or size > 8 * 1024 * 1024:
                    raise AppError('VIDEO_INVALID', 'Invalid movie metadata size/layout.')
                moov = stream.read(size-count)
            stream.seek(start + size)
        if not ftyp or not mdat or moov is None:
            raise AppError('VIDEO_INVALID', 'Missing MP4 format, video data or metadata.')
        children = list(boxes(moov))
        mvhd = next((b for k, b in children if k == b'mvhd'), b'')
        if len(mvhd) < 20 or mvhd[0] not in (0, 1) or (mvhd[0] == 1 and len(mvhd) < 32):
            raise AppError('VIDEO_INVALID', 'Invalid movie timing metadata.')
        v1 = mvhd[0] == 1
        scale = int.from_bytes(mvhd[20:24] if v1 else mvhd[12:16], 'big')
        duration = int.from_bytes(mvhd[24:32] if v1 else mvhd[16:20], 'big') / (scale or 1)
        if not scale or not math.isfinite(duration) or duration <= 0:
            raise AppError('VIDEO_INVALID', 'Invalid duration.')
        for kind, track in children:
            if kind != b'trak':
                continue
            parts = dict(boxes(track))
            mdia, tkhd = parts.get(b'mdia', b''), parts.get(b'tkhd', b'')
            hdlr = dict(boxes(mdia)).get(b'hdlr', b'')
            if hdlr[8:12] != b'vide' or len(tkhd) < 84:
                continue
            width, height = (round(int.from_bytes(tkhd[x:x+4 if x != -4 else None], 'big') / 65536) for x in (-8, -4))
            if not 0 < width <= 8192 or not 0 < height <= 8192:
                raise AppError('VIDEO_INVALID', 'Invalid video dimensions.')
            after = os.fstat(stream.fileno())
            if identity(before) != identity(after) or before.st_ctime_ns != after.st_ctime_ns or identity(before) != identity(path.stat()):
                raise AppError('VIDEO_CHANGED', 'Video changed during verification.')
            return {'bytes': before.st_size, 'sha256': h.hexdigest(), 'width': width, 'height': height, 'duration': duration}
    raise AppError('VIDEO_INVALID', 'No video track.')
