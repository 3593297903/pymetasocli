from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, model_validator

from ..contracts.records import ErrorDetail, Hashed, Uuid
from ..contracts.story import Hash, Id, StrictModel

Size = Literal['1024x1024', '1536x1024', '1024x1536', '1920x1088', '1088x1920',
               '2048x2048', '2560x1440', '2560x1707', '1707x2560', '4096x4096']


class Limits(StrictModel):
    concurrent: Annotated[int, Field(gt=0)] | None = None
    rpm: Annotated[int, Field(gt=0)] | None = None
    batch: Annotated[int, Field(gt=0)] | None = None
    source: Annotated[str, Field(min_length=1, max_length=2000)]
    checkedAt: str


class Profile(StrictModel):
    backend: Literal['api'] = 'api'
    provider: Literal['yiciyuang'] = 'yiciyuang'
    origin: Literal['https://api.yiciyuang.com'] = 'https://api.yiciyuang.com'
    model: Literal['gpt-image-2.5'] = 'gpt-image-2.5'
    quality: Literal['auto', 'low', 'medium', 'high'] = 'medium'
    n: Literal[1] = 1
    response_format: Literal['url', 'b64_json'] = 'url'
    submissionMode: Literal['all-ready'] = 'all-ready'
    boardSize: Size = '1920x1088'
    firstFrameSize: Size = '1088x1920'
    sizes: dict[Id, Size] = Field(default_factory=dict)
    providerLimits: Limits | None = None
    downloadConcurrency: Literal[2] = 2
    decodeConcurrency: Literal[2] = 2
    registrationConcurrency: Literal[1] = 1
    generationTimeoutMs: Annotated[int, Field(ge=1000, le=3600000)] = 600000
    generationTimeoutMode: Literal['exact'] | None = None
    automaticPostRetries: Literal[0] = 0
    quotaGroup: Id = 'yiciyuang-default'
    maxResponseBytes: Annotated[int, Field(ge=1024, le=45*1024*1024)] = 45*1024*1024
    maxImageBytes: Annotated[int, Field(ge=1024, le=30*1024*1024)] = 30*1024*1024
    maxTempBytes: Annotated[int, Field(gt=0, le=2**53-1)] = 32*1024**3


def timeout_seconds(profile: dict) -> float:
    value = profile['generationTimeoutMs']
    if value == 300000 and profile.get('generationTimeoutMode') != 'exact':
        value = 600000
    return min(value, 1200000) / 1000


class ImageReference(StrictModel):
    assetId: Id
    path: str
    sha256: Hash
    mime: Literal['image/png', 'image/jpeg', 'image/webp']


class ImageInput(StrictModel):
    provider: Literal['yiciyuang']
    origin: Literal['https://api.yiciyuang.com']
    route: Literal['/v1/images/edits', '/v1/images/generations']
    model: Literal['gpt-image-2.5']
    quality: Literal['auto', 'low', 'medium', 'high']
    size: Size
    n: Literal[1]
    response_format: Literal['url', 'b64_json']
    promptPath: str
    promptHash: Hash
    references: list[ImageReference]


class ImageOutput(StrictModel):
    path: str
    sha256: Hash
    bytes: Annotated[int, Field(gt=0)]
    width: Annotated[int, Field(gt=0)]
    height: Annotated[int, Field(gt=0)]
    mime: Literal['image/png', 'image/jpeg', 'image/webp']


class ImageJob(Hashed):
    operationId: Uuid
    projectId: Uuid
    planId: Uuid
    planHash: Hash
    assetId: Id
    fingerprint: Hash
    requestHash: Hash
    inputHash: Hash
    input: ImageInput
    status: Literal['prepared', 'submitting', 'response_saved', 'received', 'downloaded', 'registered', 'submit_unknown', 'rejected', 'failed']
    attempt: Annotated[int, Field(ge=1)]
    submissionProtocol: Literal['prepared-before-admission-v1'] | None = None
    preparedAt: str | None = None
    authorizationHash: Hash | None = None
    sentEpoch: Annotated[float, Field(gt=0, allow_inf_nan=False)] | None = None
    requestStartedAt: Annotated[str, Field(min_length=1)] | None = None
    timings: dict[str, float] | None = None
    retryOf: Uuid | None = None
    reportedModel: str | None = None
    resultUrl: str | None = None
    result: ImageOutput | None = None
    error: ErrorDetail | None = None
    registeredAt: str | None = None
    recoveredManually: bool | None = None

    @model_validator(mode='after')
    def submission_evidence(self):
        if self.submissionProtocol:
            if not self.preparedAt or not self.authorizationHash:
                raise ValueError('Prepared protocol requires preparation and frozen authorization evidence.')
            if datetime.fromisoformat(self.preparedAt).tzinfo is None:
                raise ValueError('Preparation time requires a timezone.')
            if self.status == 'prepared':
                if (self.sentEpoch is not None or self.requestStartedAt is not None
                    or any(k != 'prepared' for k in (self.timings or {}))
                    or self.result is not None or self.resultUrl is not None or self.registeredAt is not None):
                    raise ValueError('Prepared operation cannot contain sending or result evidence.')
                return self
        # Legacy records remain readable with their original required send fields.
        if self.sentEpoch is None or self.requestStartedAt is None:
            raise ValueError('A possible submission must retain sending timestamps.')
        if self.submissionProtocol and datetime.fromisoformat(self.requestStartedAt).tzinfo is None:
            raise ValueError('Submission intent time requires a timezone.')
        return self


class ImagePlanItem(StrictModel):
    assetId: Id
    kind: Literal['character', 'scene', 'prop', 'first_frame']
    recipeHash: Hash
    promptPath: str
    promptHash: Hash
    dependencies: list[Id]
    dependencyHashes: dict[Id, Hash | None]
    targetHash: Hash | None
    size: Size
    fingerprint: Hash
    action: Literal['reuse', 'recover', 'generate', 'blocked']
    blocker: ErrorDetail | None = None
    operationId: Uuid | None = None
    retryOf: Uuid | None = None


class ImagePlan(StrictModel):
    schemaVersion: Literal[1]
    projectId: Uuid
    planId: Uuid
    createdAt: str
    contentHash: Hash
    hashVersion: Literal['jcs-sha256-v1']
    planHash: Hash
    items: list[ImagePlanItem]
    profile: Profile
    scope: list[list[str] | tuple[str, str]]
    restartOf: Uuid | None


class ImageRun(Hashed):
    planId: Uuid
    planHash: Hash
    authorizedAt: str
    runtimeRoot: str
    items: dict[Id, Uuid | None]
    maxRequests: Annotated[int, Field(ge=0)]
    acceptUnknown: bool
    resources: dict
    replacementPlanId: Uuid | None = None
    blockers: dict[Id, ErrorDetail] | None = None
