"""CPU-only checks for the new worker geometry boundary."""
import importlib.util
from pathlib import Path

source = Path(__file__).resolve().parents[1] / 'video_detail/restore.py'
spec = importlib.util.spec_from_file_location('seed_worker', source)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
assert worker.output_spec({}, 1280, 720) == (1280, 720, 'source')
assert worker.output_spec({'outputProfile': 'source', 'outputWidth': 1920, 'outputHeight': 1080}, 1920, 1080) == (1920, 1080, 'source')
assert worker.output_spec({'outputProfile': 'qhd1440', 'outputWidth': 2560, 'outputHeight': 1440}, 1280, 720) == (2560, 1440, 'qhd1440')
invalid = [({}, 640, 480), ({'outputProfile': 'unknown'}, 1280, 720),
           ({'outputProfile': None}, 1280, 720), ({'outputProfile': 'qhd1440'}, 1280, 720),
           ({'outputProfile': 'source', 'outputWidth': 2560, 'outputHeight': 1440}, 1280, 720),
           ({'outputProfile': 'qhd1440', 'outputWidth': 2560, 'outputHeight': 1440}, 640, 480),
           ({'outputProfile': 'qhd1440', 'outputWidth': '2560', 'outputHeight': 1440}, 1280, 720),
           ({'outputProfile': 'qhd1440', 'outputWidth': True, 'outputHeight': 1440}, 1280, 720),
           ({'outputProfile': 'qhd1440', 'outputWidth': 3840, 'outputHeight': 2160}, 1280, 720)]
# The first item is a valid legacy 4:3 source and must remain supported.
assert worker.output_spec(*invalid.pop(0)) == (640, 480, 'source')
for job, width, height in invalid:
    try:
        worker.output_spec(job, width, height)
    except ValueError:
        continue
    raise AssertionError(('Expected invalid output specification', job))
print('Passed: legacy source geometry, explicit QHD and eight invalid geometry cases')
