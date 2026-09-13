"""One local worker across processes; bounded, cancellable child training."""
import functools
import multiprocessing
import os
import time
import traceback
from contextlib import contextmanager
from pathlib import Path
from . import config


@contextmanager
def worker_lease():
    path = config.DATA_DIR/'worker.lock'
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'a+b') as f:
        f.seek(0)
        if os.fstat(f.fileno()).st_size == 0:
            f.write(b'0'); f.flush()
        f.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError('Another research/evaluation worker is active') from exc
        try:
            yield
        finally:
            f.seek(0)
            if os.name == 'nt':
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(f, fcntl.LOCK_UN)


def exclusive(fn):
    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        with worker_lease():
            return fn(*args, **kwargs)
    return wrapped


def _child(connection, fn, args, kwargs):
    try:
        connection.send((True, fn(*args, **kwargs)))
    except BaseException:
        connection.send((False, traceback.format_exc()))
    finally:
        connection.close()


def bounded(fn, *args, should_cancel=None, timeout=None, **kwargs):
    ctx = multiprocessing.get_context('spawn')
    parent, child = ctx.Pipe(duplex=False)
    process = ctx.Process(target=_child, args=(child,fn,args,kwargs))
    process.start(); child.close()
    deadline = time.monotonic() + (config.MAX_RUNTIME_SECONDS if timeout is None else timeout)
    try:
        while not parent.poll(0.1):
            if should_cancel and should_cancel():
                raise InterruptedError('Training cancelled')
            if time.monotonic() >= deadline:
                raise TimeoutError('Training exceeded MAX_RUNTIME_SECONDS')
            if not process.is_alive():
                raise RuntimeError(f'Training process exited: {process.exitcode}')
        try:
            ok, value = parent.recv()
        except EOFError as exc:
            raise RuntimeError('Training process exited without a result') from exc
        if not ok:
            raise RuntimeError(value)
        return value
    finally:
        parent.close()
        process.join(timeout=1)
        if process.is_alive():
            process.terminate(); process.join(timeout=5)
        if process.is_alive():
            process.kill(); process.join()
