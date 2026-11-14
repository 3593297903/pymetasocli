import math
import re
from typing import Annotated, Any, Literal, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError, model_validator

from ..domain.errors import AppError
from ..persistence.codec import MAX_INT, validate_values

Id = Annotated[str, StringConstraints(min_length=1, max_length=80, pattern=r'^[a-z0-9][a-z0-9_-]*$')]
Hash = Annotated[str, StringConstraints(pattern=r'^[a-f0-9]{64}$')]
Count = Annotated[int, Field(ge=0, le=MAX_INT)]


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid', hide_input_in_errors=True)

    @model_validator(mode='before')
    @classmethod
    def check_values(cls, value: Any) -> Any:
        validate_values(value)
        if isinstance(value, dict):
            for key, field in cls.model_fields.items():
                annotation = field.annotation
                if get_origin(annotation) is Literal and any(type(v) is int for v in get_args(annotation)) and key in value and type(value[key]) is not int:
                    raise ValueError('Integer literal requires an integer')
            for key in ('id', 'assetId', 'episodeId', 'segmentId'):
                if isinstance(value.get(key), str) and re.fullmatch(r'(con|prn|aux|nul|com[0-9]|lpt[0-9])', value[key], re.I):
                    raise ValueError('Reserved identifier')
        return value


class Reference(StrictModel):
    assetId: Id
    role: Literal['reference_image', 'first_frame']


class Cue(StrictModel):
    start: Count
    end: Annotated[int, Field(gt=0, le=MAX_INT)]


class Narration(StrictModel):
    assetId: Id
    cues: Annotated[list[Cue], Field(min_length=1, max_length=100)]


class Parameters(StrictModel):
    model: Literal['MiniMax-H3'] = 'MiniMax-H3'
    resolution: Literal['768P', '2K'] = '768P'
    ratio: Literal['adaptive', '21:9', '16:9', '4:3', '1:1', '3:4', '9:16'] = '9:16'
    contextIr: bool = True
    watermark: bool = False


class Recipe(StrictModel):
    assetId: Id
    kind: Literal['character', 'scene', 'prop', 'first_frame', 'narration']
    prompt: Annotated[str, Field(min_length=1, max_length=32000)]
    exactText: list[str] = Field(default_factory=list)
    dependencies: list[Id] = Field(default_factory=list)


class Media(StrictModel):
    path: str
    sha256: Hash
    bytes: Annotated[int, Field(gt=0, le=MAX_INT)]
    provenance: Literal['user', 'imagegen']
    transport: Literal['data', 'url'] = 'data'
    url: str | None = None
    mime: Literal['image/png', 'image/jpeg', 'image/webp', 'audio/mpeg', 'audio/wav']
    width: Annotated[int, Field(gt=0)] | None = None
    height: Annotated[int, Field(gt=0)] | None = None
    duration: Annotated[float, Field(ge=2, le=15)] | None = None
    sampleRate: Annotated[int, Field(gt=0)] | None = None
    channels: Annotated[int, Field(ge=1, le=2)] | None = None

    @model_validator(mode='after')
    def roles(self):
        if (self.transport == 'url') != bool(self.url):
            raise ValueError('URL transport identity')
        if self.mime.startswith('image/'):
            if self.width is None or self.height is None or self.duration is not None:
                raise ValueError('Image metadata')
        elif self.duration is None or self.channels is None or self.sampleRate is None or self.width is not None:
            raise ValueError('Audio metadata')
        return self


class Asset(StrictModel):
    recipe: Recipe
    recipeHash: Hash
    media: Media | None


class DraftSegment(StrictModel):
    id: Id
    start: Count
    end: Annotated[int, Field(gt=0, le=MAX_INT)]
    duration: Annotated[int | float, Field(gt=0, le=15)]
    prompt: Annotated[str, Field(min_length=1)] | None = None
    references: Annotated[list[Reference], Field(max_length=9)] = Field(default_factory=list)
    parameters: Parameters = Field(default_factory=Parameters)
    narration: Narration | None = None


class Segment(DraftSegment):
    duration: Annotated[int, Field(ge=4, le=15)]
    targetDurationSeconds: Annotated[int | float, Field(gt=0, le=15)] | None = None
    prompt: Annotated[str, Field(min_length=1)]
    promptHash: Hash

    @model_validator(mode='after')
    def matching_duration(self):
        if self.targetDurationSeconds is not None and math.ceil(self.targetDurationSeconds) != self.duration:
            raise ValueError('Duration mismatch')
        return self


class Source(StrictModel):
    origin: str
    rawPath: str
    rawHash: Hash
    textPath: str
    textHash: Hash


class Episode(StrictModel):
    id: Id
    kind: Literal['script', 'video-prompts']
    offsetEncoding: Literal['utf16'] = 'utf16'
    source: Source
    segments: Annotated[list[Segment], Field(min_length=1, max_length=1000)]


class Manifest(StrictModel):
    schemaVersion: Literal[1]
    owner: Literal['metasocli-py']
    hashVersion: Literal['jcs-sha256-v1']
    projectId: Annotated[str, StringConstraints(pattern=r'^[0-9a-f-]{36}$')]
    name: Annotated[str, Field(min_length=1, max_length=500)]
    revision: Count
    episodes: Annotated[list[Episode], Field(max_length=1000)]
    assets: Annotated[list[Asset], Field(max_length=2000)]


class ImportDraft(StrictModel):
    episodeId: Id
    kind: Literal['script', 'video-prompts']
    source: Annotated[str, Field(min_length=1)]
    offsetEncoding: Literal['utf16'] = 'utf16'
    segments: Annotated[list[DraftSegment], Field(min_length=1, max_length=1000)]
    recipes: Annotated[list[Recipe], Field(max_length=2000)] = Field(default_factory=list)


def parse(schema: type[StrictModel], value: Any) -> dict:
    try:
        model = schema.model_validate(value)
        # Preserve explicitly present null/false/zero. Defaults required by business schemas
        # are materialized, optional fields remain absent when not supplied.
        result = model.model_dump(exclude_unset=True)
        return result
    except ValidationError as error:
        paths = ['.'.join(str(x) for x in item['loc']) or '(root)'
                 for item in error.errors(include_input=False, include_context=False, include_url=False)]
        raise AppError('INVALID_INPUT', 'Contract validation failed at ' + ', '.join(paths[:20])) from None
