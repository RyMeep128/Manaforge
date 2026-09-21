from PyQt6.QtCore import QLockFile
from pathlib import Path


def acquire_project_lock(path):
    lock = QLockFile(str(Path(path).resolve()) + '.lock')
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        raise OSError('This print project is open in another process. Close it and retry.')
    return lock
