"""Experimental per-run verification cache keyed by exact current bytes.

Every lookup still uses the original stable-file reader. No mtime-only shortcut,
no cached mutable quota ledger, and no cache surviving the Quota instance.
"""
import copy
from collections import OrderedDict

from ..application.story import MANIFEST, STATE, validate_story_bytes
from ..contracts.records import validate_record
from ..domain.errors import AppError
from ..persistence.codec import loads, verify
from ..persistence.files import project_path, read_stable
from .contracts import ImagePlan, ImageRun


class PreparedProofCache:
    def __init__(self, max_entries=4, max_bytes=8*1024*1024):
        self.entries = OrderedDict()
        self.max_entries, self.max_bytes = max_entries, max_bytes
        self.total_bytes = 0
        self.hits = self.misses = 0

    def _get(self, path, validator):
        raw = read_stable(path)
        key = str(path)
        previous = self.entries.get(key)
        if previous is not None and previous[0] == raw:
            self.hits += 1
            self.entries.move_to_end(key)
            return previous[1]
        self.misses += 1
        if previous is not None:
            self.total_bytes -= len(previous[0])
            del self.entries[key]
        value = validator(raw)
        if len(raw) <= self.max_bytes:
            while self.entries and (len(self.entries) >= self.max_entries or self.total_bytes+len(raw) > self.max_bytes):
                _, (removed, _) = self.entries.popitem(last=False)
                self.total_bytes -= len(removed)
            self.entries[key] = (raw, value)
            self.total_bytes += len(raw)
        return value

    def plan(self, root, plan_id):
        path = project_path(root, f'{STATE}/image-plans/{plan_id}.json')
        def validated(raw):
            plan = verify(loads(raw), 'planHash')
            validate_record(ImagePlan, plan)
            return plan
        plan = self._get(path, validated)
        story = self._get(project_path(root, MANIFEST), validate_story_bytes)
        if plan['planId'] != plan_id or plan['projectId'] != story['projectId']:
            raise AppError('IMAGE_PLAN_IDENTITY', 'Image plan belongs to another story.')
        return copy.deepcopy(plan)

    def run(self, path):
        return copy.deepcopy(self._get(path, lambda raw: validate_record(ImageRun, verify(loads(raw)))))
