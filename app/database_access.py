"""Allow ordinary connections concurrently; give restore exclusive access."""
import threading
from contextlib import contextmanager


class DatabaseGate:
    def __init__(self):
        self.condition = threading.Condition()
        self.readers = {}
        self.writer = None
        self.waiting = 0

    def acquire(self):
        owner = threading.get_ident()
        with self.condition:
            while self.writer not in (None, owner) or (self.waiting and owner not in self.readers and self.writer != owner):
                self.condition.wait()
            self.readers[owner] = self.readers.get(owner, 0) + 1

    def release(self):
        owner = threading.get_ident()
        with self.condition:
            self.readers[owner] -= 1
            if not self.readers[owner]:
                del self.readers[owner]
            self.condition.notify_all()

    def acquire_exclusive(self):
        owner = threading.get_ident()
        with self.condition:
            if owner in self.readers:
                raise RuntimeError("Close database connections before starting restore.")
            self.waiting += 1
            try:
                while self.writer is not None or self.readers:
                    self.condition.wait()
                self.writer = owner
            finally:
                self.waiting -= 1

    def release_exclusive(self):
        with self.condition:
            if self.writer != threading.get_ident():
                raise RuntimeError("Restore lock belongs to another thread.")
            self.writer = None
            self.condition.notify_all()

    @contextmanager
    def access(self):
        self.acquire()
        try:
            yield
        finally:
            self.release()
