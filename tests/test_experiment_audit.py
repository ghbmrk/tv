import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.audit_experiment import audit, GATES, unique_object

ROOT = Path(__file__).resolve().parent.parent


class ExperimentAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.target = dict(model='fixture-model', installed_build='fixture-build', board_id='fixture-board', board_revision='fixture-revision',
                           one_connect_model='fixture-box', one_connect_assembly='fixture-assembly',
                           power_label_code='fixture-power', panel_id='fixture-panel')
        self.artifact = self.file('image', b'synthetic image, never a hardware image')
        self.packet = dict(schema_version=2, target=self.target, artifact=self.artifact, gates=[
            dict(id=g, status='documented', scope=dict(target=self.target.copy(), artifact_sha256=self.artifact['sha256']),
                 evidence=[self.file(g, ('synthetic evidence for ' + g).encode())]) for g in GATES])

    def file(self, name, data):
        (self.root / name).write_bytes(data)
        return dict(path=name, bytes=len(data), sha256=hashlib.sha256(data).hexdigest())

    def test_complete_fixture_never_claims_safety_or_authorization(self):
        result = audit(self.packet, self.root)
        self.assertTrue(result['review_packet_complete'])
        self.assertFalse(result['hardware_safety_verified'])
        self.assertFalse(result['authorization_granted'])
        self.assertFalse(result['device_accessed'])

    def test_current_target_is_blocked_and_cli_exits_nonzero(self):
        path = ROOT / 'docs/deployment/experiment-packet.json'
        packet = json.loads(path.read_text())
        result = audit(packet, path.parent)
        self.assertFalse(result['review_packet_complete'])
        self.assertIn('target:board_id', result['blockers'])
        self.assertIn('recovery:unverified', result['blockers'])
        command = subprocess.run([sys.executable, str(ROOT / 'tools/audit_experiment.py'), str(path)], capture_output=True, text=True)
        self.assertEqual(command.returncode, 2)
        self.assertFalse(json.loads(command.stdout)['authorization_granted'])

    def test_external_labels_do_not_replace_compute_board_or_panel_identity(self):
        packet = copy.deepcopy(self.packet)
        for field in ('board_id', 'board_revision', 'panel_id'):
            packet['target'][field] = None
        packet['gates'] = [dict(id=g, status='unverified', scope=None, evidence=[]) for g in GATES]
        result = audit(packet, self.root)
        self.assertFalse(result['review_packet_complete'])
        for field in ('board_id', 'board_revision', 'panel_id'):
            self.assertIn('target:' + field, result['blockers'])

    def test_stale_target_image_or_changed_proof_is_rejected(self):
        for field in self.target:
            packet = copy.deepcopy(self.packet)
            packet['gates'][0]['scope']['target'][field] = 'different'
            with self.subTest(field=field), self.assertRaises(ValueError):
                audit(packet, self.root)
        packet = copy.deepcopy(self.packet)
        packet['artifact'] = self.file('new-image', b'new image')
        with self.assertRaises(ValueError):
            audit(packet, self.root)
        (self.root / GATES[0]).write_bytes(b'x' * self.packet['gates'][0]['evidence'][0]['bytes'])
        with self.assertRaises(ValueError):
            audit(self.packet, self.root)

    def test_missing_duplicate_unknown_gates_and_claims_without_evidence_are_rejected(self):
        variants = []
        p = copy.deepcopy(self.packet); p['gates'].pop(); variants.append(p)
        p = copy.deepcopy(self.packet); p['gates'][0] = p['gates'][1]; variants.append(p)
        p = copy.deepcopy(self.packet); p['gates'][0]['id'] = 'skip-recovery'; variants.append(p)
        p = copy.deepcopy(self.packet); p['gates'][0]['evidence'] = []; variants.append(p)
        p = copy.deepcopy(self.packet); p['gates'][0]['status'] = 'verified'; variants.append(p)
        p = copy.deepcopy(self.packet); p['target']['board_id'] = None; variants.append(p)
        p = copy.deepcopy(self.packet); p['authorize_write'] = True; variants.append(p)
        p = copy.deepcopy(self.packet); p['schema_version'] = 1; variants.append(p)
        for p in variants:
            with self.assertRaises(ValueError):
                audit(p, self.root)
        with self.assertRaises(ValueError):
            json.loads('{"status": "unverified", "status": "documented"}', object_pairs_hook=unique_object)

    def test_paths_links_missing_files_and_resource_bounds_are_rejected(self):
        (self.root / 'linked').symlink_to(self.root / 'image')
        for path in ('../image', '/image', './image', 'a/../image', 'linked', 'missing'):
            p = copy.deepcopy(self.packet); p['artifact']['path'] = path
            with self.subTest(path=path), self.assertRaises((ValueError, OSError)):
                audit(p, self.root)
        for size in (True, -1, 8 * 1024**3 + 1):
            p = copy.deepcopy(self.packet); p['artifact']['bytes'] = size
            with self.assertRaises(ValueError):
                audit(p, self.root)

    def test_cli_rejects_special_file_without_reading_or_connecting(self):
        path = self.root / 'pipe'
        os.mkfifo(path)
        result = subprocess.run([sys.executable, str(ROOT / 'tools/audit_experiment.py'), str(path)],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 3)
        self.assertFalse(json.loads(result.stdout)['device_accessed'])


if __name__ == '__main__':
    unittest.main()
