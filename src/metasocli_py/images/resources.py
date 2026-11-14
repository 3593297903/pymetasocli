"""Admission budgets checked before any image POST, never a hidden worker cap."""
import ctypes
import os
import shutil
import sys
from pathlib import Path

from ..domain.errors import AppError


def preflight(root: Path, count: int, profile: dict) -> dict:
    disk = count * (profile['maxResponseBytes'] + 3*profile['maxImageBytes'] + 256*1024)
    memory = 2 * (profile['maxResponseBytes']*4 + profile['maxImageBytes']*3) + count*256*1024
    handles = count*3 + 128
    available = None
    if sys.platform == 'win32':
        class Memory(ctypes.Structure):
            _fields_ = [('length', ctypes.c_uint32), ('load', ctypes.c_uint32),
                        *[(name, ctypes.c_uint64) for name in ('total', 'available', 'pageTotal', 'pageAvailable', 'virtualTotal', 'virtualAvailable', 'extended')]]
        info = Memory()
        info.length = ctypes.sizeof(info)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(info)):
            raise AppError('IMAGE_RESOURCE_LIMIT', 'Cannot establish available memory before submission.')
        available = info.available
        observed = ctypes.c_uint32()
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        kernel.GetProcessHandleCount.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
        if not kernel.GetProcessHandleCount(kernel.GetCurrentProcess(), ctypes.byref(observed)) or observed.value + handles > 65536:
            raise AppError('IMAGE_RESOURCE_LIMIT', 'Handle preflight budget exceeded.')
    else:
        import resource
        available = os.sysconf('SC_AVPHYS_PAGES') * os.sysconf('SC_PAGE_SIZE')
        limit, _ = resource.getrlimit(resource.RLIMIT_NOFILE)
        if limit != resource.RLIM_INFINITY and handles > limit:
            raise AppError('IMAGE_RESOURCE_LIMIT', 'File descriptor budget cannot support all-ready dispatch.')
    free = shutil.disk_usage(root).free
    if disk > profile['maxTempBytes'] or disk > free or memory > available:
        raise AppError('IMAGE_RESOURCE_LIMIT', 'Insufficient disk/memory budget for the full frozen scope; no POST sent.')
    return {'requests': count, 'estimatedDiskBytes': disk, 'estimatedMemoryBytes': memory,
            'estimatedHandles': handles, 'availableDiskBytes': free, 'availableMemoryBytes': available}
