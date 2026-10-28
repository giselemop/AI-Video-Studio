"""Offline regression: range integrity, resuming and path/overwrite boundaries."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from download_assets import atomic_replace, download, target_path


class Response:
    def __init__(self, data, start, end, size, status=206):
        self.data = data
        self.status_code = status
        self.headers = {"Content-Range": f"bytes {start}-{end}/{size}"}

    def __enter__(self): return self
    def __exit__(self, *args): pass
    def raise_for_status(self): pass
    def iter_content(self, size): yield self.data


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix="videostudio-download-test-")
        self.root = Path(self.folder.name)
        self.data = b"verified-model-data-0123456789"
        self.asset = dict(repository="test/public", revision="fixed", file="model.gguf", target="diffusion_models/model.gguf",
                          size=len(self.data), sha256=hashlib.sha256(self.data).hexdigest())

    def tearDown(self): self.folder.cleanup()

    def response(self, url, headers, **kwargs):
        start, end = map(int, headers["Range"][6:].split("-"))
        return Response(self.data[start:end + 1], start, end, len(self.data))

    def test_ranges_are_verified_and_existing_models_not_redownloaded(self):
        with patch("download_assets.requests.get", side_effect=self.response) as request:
            download(self.asset, self.root, 2, 8)
            count = request.call_count
            download(self.asset, self.root, 2, 8)
            self.assertEqual(count, request.call_count)
        self.assertEqual(target_path(self.root, self.asset["target"]).read_bytes(), self.data)

    def test_resume_skips_only_durable_completed_chunks(self):
        target = target_path(self.root, self.asset["target"])
        target.parent.mkdir()
        partial = target.with_name(target.name + ".part")
        partial.write_bytes(self.data[:8] + b"\0" * (len(self.data) - 8))
        target.with_name(target.name + ".download.json").write_text(json.dumps(dict(size=len(self.data), sha256=self.asset["sha256"], chunk_size=8, completed=[0])))
        with patch("download_assets.requests.get", side_effect=self.response) as request:
            download(self.asset, self.root, 2, 8)
            self.assertTrue(all(call.kwargs["headers"]["Range"] != "bytes=0-7" for call in request.call_args_list))
        self.assertEqual(target.read_bytes(), self.data)

    def test_non_range_response_never_publishes_model(self):
        with patch("download_assets.requests.get", return_value=Response(self.data, 0, 7, len(self.data), status=200)):
            with self.assertRaises(ValueError): download(self.asset, self.root, 1, 8)
        self.assertFalse(target_path(self.root, self.asset["target"]).exists())

    def test_existing_mismatched_file_is_preserved(self):
        target = target_path(self.root, self.asset["target"])
        target.parent.mkdir()
        target.write_bytes(b"existing-user-model")
        with self.assertRaises(ValueError): download(self.asset, self.root, 1, 8)
        self.assertEqual(target.read_bytes(), b"existing-user-model")

    def test_targets_cannot_escape_model_root(self):
        with self.assertRaises(ValueError): target_path(self.root, "../another/model.gguf")
        with self.assertRaises(ValueError): target_path(self.root, "model.py")

    def test_transient_reader_lock_does_not_lose_checkpoint(self):
        source, target = self.root / 'new.tmp', self.root / 'state.json'
        source.write_text('new'); target.write_text('old')
        import os
        replace = os.replace
        calls = []
        def temporarily_locked(a, b):
            calls.append(1)
            if len(calls) < 3: raise PermissionError('transient read handle')
            replace(a, b)
        with patch('download_assets.os.replace', side_effect=temporarily_locked), patch('download_assets.time.sleep'):
            atomic_replace(source, target)
        self.assertEqual(target.read_text(), 'new')
        self.assertEqual(len(calls), 3)

    def test_persistent_access_denial_preserves_both_files(self):
        source, target = self.root / 'new.tmp', self.root / 'state.json'
        source.write_text('new'); target.write_text('old')
        with patch('download_assets.os.replace', side_effect=PermissionError('denied')) as replace, patch('download_assets.time.sleep'):
            with self.assertRaises(PermissionError): atomic_replace(source, target)
        self.assertEqual(replace.call_count, 12)
        self.assertEqual(target.read_text(), 'old')
        self.assertEqual(source.read_text(), 'new')


if __name__ == "__main__": unittest.main()
