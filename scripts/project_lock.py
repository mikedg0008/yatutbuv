"""OS-managed lock: released automatically even if the program crashes."""
from contextlib import contextmanager
import os
from pathlib import Path
from travel_core import TravelError


@contextmanager
def project_lock(root):
    path = Path(root)/'backups/.project-lock'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as f:
        if f.tell() == 0:
            f.write(b'0')
            f.flush()
        f.seek(0)
        locked = False
        try:
            try:
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except OSError:
                raise TravelError('This project is open in another window or command. Close it and retry.') from None
            yield
        finally:
            if locked:
                f.seek(0)
                if os.name == 'nt':
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(f, fcntl.LOCK_UN)
