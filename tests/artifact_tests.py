"""Read-only provenance diagnostics without engines or model loading."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from genseki.artifacts import create_manifest, portable_value, sha256_file, verify_manifest


class ArtifactTests(unittest.TestCase):
    def test_portable_metadata(self):
        self.assertEqual(portable_value(ROOT, ROOT/'build/engine.exe'), 'build/engine.exe')
        self.assertEqual(portable_value(ROOT, 'C:/Users/private/engine.exe'),
                         '<redacted-host-metadata>')
    def manifest(self, root):
        (root/'engine').write_bytes(b'engine fixture')
        return create_manifest(root, dict(executable='engine', model=None),
            provenance=dict(kind='imported-binary'),
            effective_settings=dict(requested=dict(threads=1),
                                    verified=dict(threads=1), evidence='options response'))

    def test_match_mismatch_missing_and_no_repair(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = self.manifest(root)
            self.assertEqual(verify_manifest(root, manifest), [])
            (root/'engine').write_bytes(b'changed')
            self.assertIn('SHA256 mismatch', ' '.join(verify_manifest(root, manifest)))
            self.assertEqual((root/'engine').read_bytes(), b'changed')
            (root/'engine').unlink()
            self.assertIn('missing', ' '.join(verify_manifest(root, manifest)))
            self.assertFalse((root/'engine').exists())

    def test_source_build_and_settings_evidence_required(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = self.manifest(root)
            manifest['provenance']['kind'] = 'verified-source-build'
            self.assertIn('missing build provenance', ' '.join(verify_manifest(root, manifest)))
            (root/'source').write_bytes(b'source')
            manifest['provenance'].update(revision='abc',compiler='rustc pinned',
                dependencies=['pinned'],build_command=['cargo','build'],build_exit_code=0,
                source_files={'source': sha256_file(root/'source')})
            self.assertEqual(verify_manifest(root, manifest), [])
            (root/'source').write_bytes(b'new challenger source')
            self.assertTrue(verify_manifest(root, manifest))
            self.assertEqual(verify_manifest(root, manifest, check_sources=False), [])
            manifest['effective_settings']['verified']['threads'] = 2
            self.assertIn('differ', ' '.join(verify_manifest(root, manifest)))

    def test_unsafe_paths_and_private_metadata_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            original = self.manifest(root)
            for path in ('../engine', 'C:/Users/private/engine', '/etc/passwd'):
                manifest = copy.deepcopy(original)
                manifest['artifacts']['executable']['path'] = path
                self.assertTrue(verify_manifest(root, manifest))
            original['provenance']['compiler'] = 'C:\\Users\\private\\compiler'
            self.assertIn('identifying path', ' '.join(verify_manifest(root, original)))

    def test_doctor_malformed_input_is_sanitized(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'manifest.json'
            path.write_text('{', encoding='utf-8')
            result = subprocess.run([sys.executable, '-B', '-m', 'genseki.artifacts',
                                     str(path)], cwd=ROOT, capture_output=True,
                                    text=True, timeout=10)
            self.assertEqual(result.returncode, 1)
            output = json.loads(result.stdout)
            self.assertFalse(output['valid'])
            self.assertNotIn(str(path), result.stdout+result.stderr)


if __name__ == '__main__':
    unittest.main()
