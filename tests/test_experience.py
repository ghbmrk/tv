import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from sovereign_tv.model import Invalid, validate
from sovereign_tv.store import Conflict, Store
from sovereign_tv.server import handler

ROOT = Path(__file__).resolve().parent.parent


class ExperienceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.initial = json.loads((ROOT / 'examples/experience.json').read_text())
        self.path = Path(self.temp.name) / 'state.sqlite3'
        self.store = Store(self.path, self.initial)

    def request(self, name='edit-1', base=1):
        doc = copy.deepcopy(self.initial)
        doc['title'] = 'Evening'
        doc['sections'][0]['items'][0]['visible'] = False
        return {'request_id': name, 'base_revision': base, 'experience': doc}

    def test_malformed_unicode_is_refused_without_a_revision_or_receipt(self):
        for index, title in enumerate(('Bad \ud800', 'Bad \ud801', 'Bad \udc00')):
            request = self.request(name='unicode-' + str(index))
            request['experience']['title'] = title
            with self.assertRaises(Invalid):
                self.store.apply(request)
            self.assertIsNone(self.store.receipt(request['request_id']))
            self.assertEqual(self.store.state()['revision'], 1)
        boundary = self.request()['experience']
        boundary['title'] = '\U0001f3ac' * 120
        validate(boundary)
        boundary['title'] += '\U0001f3ac'
        with self.assertRaises(Invalid):
            validate(boundary)
        request = self.request(name='valid-unicode')
        request['experience']['title'] = 'Film \U0001f3ac'
        self.store.apply(request)
        self.assertEqual(self.store.state()['experience']['title'], request['experience']['title'])

    def test_preview_does_not_apply_and_application_survives_restart(self):
        request = self.request()
        self.assertFalse(self.store.preview(request)['applied'])
        self.assertEqual(self.store.state()['revision'], 1)
        result = self.store.apply(request)
        reopened = Store(self.path, self.initial)
        self.assertEqual(reopened.state()['experience'], request['experience'])
        self.assertEqual(reopened.receipt('edit-1'), result)

    def test_lost_reply_duplicate_never_applies_twice(self):
        first = self.store.apply(self.request())
        self.assertEqual(Store(self.path, self.initial).apply(self.request()), first)
        self.assertEqual(self.store.state()['revision'], 2)
        changed = self.request()
        changed['experience']['title'] = 'Different'
        with self.assertRaises(Conflict):
            self.store.apply(changed)

    def test_concurrent_edit_and_undo_do_not_overwrite_newer_state(self):
        self.store.apply(self.request())
        with self.assertRaises(Conflict):
            self.store.apply(self.request('stale'))
        self.store.apply(self.request('newer', 2))
        with self.assertRaises(Conflict):
            self.store.apply({'request_id': 'undo', 'base_revision': 2, 'restore_revision': 1}, undo=True)
        self.assertEqual(self.store.state()['revision'], 3)

    def test_undo_creates_revision_and_is_idempotent(self):
        self.store.apply(self.request())
        request = {'request_id': 'undo', 'base_revision': 2, 'restore_revision': 1}
        result = self.store.apply(request, undo=True)
        self.assertEqual(self.store.state()['experience'], self.initial)
        self.assertEqual(self.store.apply(request, undo=True), result)
        self.assertEqual(self.store.state()['revision'], 3)

    def test_concurrent_writers_only_one_base_revision_wins(self):
        outcomes = []
        def write(name):
            try:
                self.store.apply(self.request(name))
                outcomes.append('applied')
            except Conflict:
                outcomes.append('conflict')
        threads = [threading.Thread(target=write, args=(str(i),)) for i in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertCountEqual(outcomes, ['applied', 'conflict'])

    def test_rejects_executable_or_remote_content_and_invalid_bounds(self):
        for change in ('script', 'target', 'scale', 'empty', 'duplicate', 'boolean', 'unknown'):
            doc = copy.deepcopy(self.initial)
            if change == 'script': doc['script'] = 'execute()'
            if change == 'target': doc['sections'][0]['items'][0]['target'] = 'https://example.com'
            if change == 'scale': doc['settings']['text_scale'] = float('nan')
            if change == 'empty': doc['sections'] = []
            if change == 'duplicate': doc['sections'][0]['items'][0]['id'] = 'watch'
            if change == 'boolean': doc['settings']['artwork_interval_seconds'] = True
            if change == 'unknown': doc['settings']['shell'] = 'sh'
            with self.subTest(change=change), self.assertRaises(Invalid):
                validate(doc)


class ApiTests(unittest.TestCase):
    request = ExperienceTests.request

    def setUp(self):
        ExperienceTests.setUp(self)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler(self.store, 'synthetic-test-token'))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)
        self.url = f'http://127.0.0.1:{self.server.server_port}'

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def call(self, path, data=None, **headers):
        request = urllib.request.Request(self.url + path, data=json.dumps(data).encode() if data is not None else None,
            headers={'Authorization': 'Bearer synthetic-test-token', 'Content-Type': 'application/json', **headers})
        try:
            response = urllib.request.urlopen(request)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read())

    def test_auth_origin_and_host_boundary(self):
        for headers, expected in [({'Authorization': ''}, 401), ({'Origin': 'https://foreign.example'}, 403), ({'Host': 'rebound.example'}, 403)]:
            self.assertEqual(self.call('/api/state', **headers)[0], expected)
        self.assertEqual(self.call('/api/state')[0], 200)

    def test_api_apply_conflict_receipt_and_undo(self):
        self.assertEqual(self.call('/api/preview', self.request())[0], 200)
        self.assertEqual(self.call('/api/apply', self.request())[0], 200)
        self.assertEqual(self.call('/api/apply', self.request('stale'))[0], 409)
        self.assertEqual(self.call('/api/receipts/edit-1')[1]['revision'], 2)
        self.assertEqual(self.call('/api/undo', {'request_id': 'u', 'base_revision': 2, 'restore_revision': 1})[0], 200)

    def test_malformed_requests_fail_without_mutation(self):
        for data in (None, [], {'request_id': 'wrong'}, {'unexpected': '<script>'}):
            if data is not None:
                self.assertEqual(self.call('/api/apply', data)[0], 400)
        self.assertEqual(self.call('/api/apply', self.request(), **{'Content-Type': 'text/plain'})[0], 415)
        self.assertEqual(self.store.state()['revision'], 1)


if __name__ == '__main__':
    unittest.main()
