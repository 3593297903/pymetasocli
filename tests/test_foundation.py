import math
import struct

import pytest
from hypothesis import given
from hypothesis import strategies as st

from metasocli_py.contracts.story import Parameters, parse
from metasocli_py.domain.errors import AppError
from metasocli_py.domain.text import normalize_text, offset_map, utf16_length, utf16_slice
from metasocli_py.persistence.codec import canonical, digest, loads
from metasocli_py.resources import append_denoise


def test_utf16_source_and_no_trimming():
    assert normalize_text(b'\xef\xbb\xbf A\r\nB\r\n') == ' A\nB\n'
    assert utf16_length('甲😀乙') == 4
    assert utf16_slice('甲😀乙', 3, 4) == '乙'
    with pytest.raises(AppError):
        utf16_slice('甲😀乙', 1, 2)
    with pytest.raises(AppError):
        normalize_text('\ud800')


@given(st.text(alphabet=st.characters(blacklist_categories=('Cs',)), max_size=80))
def test_utf16_round_trip(text):
    offsets = offset_map(text)
    assert utf16_slice(text, 0, utf16_length(text)) == text
    assert ''.join(utf16_slice(text, a, b) for a, b in zip(list(offsets), list(offsets)[1:])) == text


def test_jcs_vectors_and_distinctions():
    assert canonical({'numbers': [333333333.33333329, 1e30, 4.50, 2e-3, 1e-27]}) == b'{"numbers":[333333333.3333333,1e+30,4.5,0.002,1e-27]}'
    assert canonical({'a': 2, 'A': 3, 'value': 1e-7, 'z': -0.0, 'Z': 1.0}) == b'{"A":3,"Z":1,"a":2,"value":1e-7,"z":0}'
    assert len({digest(x) for x in ({}, {'x': None}, {'x': False}, {'x': 0})}) == 4
    for invalid in (math.nan, math.inf, 2**53, '\udfff'):
        with pytest.raises(AppError):
            canonical(invalid)


@pytest.mark.parametrize('source,yaml_input', [(' {"a":1,"a":2}', False), ('a: 1\na: 2', True),
    ('a: &x [1]\nb: *x', True), ('a: !!str 2', True), ('{"a":NaN}', False)])
def test_reject_ambiguous_input(source, yaml_input):
    with pytest.raises(AppError):
        loads(source, yaml_input=yaml_input)


def test_strict_types():
    assert loads('a: yes\nb: 2026-11-13\nc: false\nd: 01', yaml_input=True) == {'a': 'yes', 'b': '2026-11-13', 'c': False, 'd': '01'}
    for value in ({'watermark': 0}, {'contextIr': 'true'}, {'unknown': 1}):
        with pytest.raises(AppError):
            parse(Parameters, value)


def test_denoise_idempotent_and_type_specific():
    prompt = append_denoise('character', '人物完整配方')
    assert append_denoise('character', prompt) == prompt
    with pytest.raises(AppError):
        append_denoise('scene', prompt)
    assert append_denoise('narration', ' 音频\n') == ' 音频\n'


def test_audio_pcm_float_vbr_id3_and_false_metadata():
    from metasocli_py.media.inspect import audio_info
    def wav(seconds=3, format_code=1):
        bits = 16 if format_code == 1 else 32
        align = bits//8
        data = bytes(seconds*8000*align)
        fmt = struct.pack('<HHIIHH', format_code, 1, 8000, 8000*align, align, bits)
        return b'RIFF'+struct.pack('<I', len(data)+36)+b'WAVEfmt '+struct.pack('<I', 16)+fmt+b'data'+struct.pack('<I', len(data))+data
    frames = []
    for index in range(120):
        bitrate = 160000 if index % 2 else 128000
        frames.append(bytes([255, 251, 160 if index % 2 else 144, 0])+bytes(144*bitrate//44100-4))
    mp3 = b''.join(frames)
    assert audio_info(wav())['duration'] == 3
    assert audio_info(wav(4, 3))['duration'] == 4
    assert audio_info(mp3)['duration'] == 120*1152/44100
    tagged = bytes([73, 68, 51, 4, 0, 0, 0, 0, 0, 3, 0, 0, 0])+mp3+b'TAG'+bytes(125)
    assert audio_info(tagged)['mime'] == 'audio/mpeg'
    xing = bytearray(mp3)
    xing[36:48] = b'Xing'+struct.pack('>II', 1, 119)
    assert audio_info(xing)['duration'] == 119*1152/44100
    struct.pack_into('>I', xing, 44, 800)
    wrong_align = bytearray(wav())
    struct.pack_into('<H', wrong_align, 32, 1)
    for invalid in [wav(1), wav(16), wav()[:-1], mp3[:-1], wrong_align, xing, b'not audio']:
        with pytest.raises(AppError):
            audio_info(invalid)
