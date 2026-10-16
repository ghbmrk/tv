import copy
import json
from pathlib import Path
import tempfile
import unittest
from sovereign_tv.model import Invalid, validate, artwork_refs
from sovereign_tv.store import Store


class StorybookTests(unittest.TestCase):
    def setUp(self):
        self.doc = json.loads(Path('examples/storybook.json').read_text())

    def test_curated_order_visibility_removal_persistence_and_undo(self):
        validate(self.doc)
        self.assertEqual(len(self.doc['sections'][0]['items']), 6)
        self.assertEqual(len(self.doc['sections'][1]['items']), 6)
        self.assertTrue(all(item['playback'] is None for item in self.doc['sections'][0]['items']))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state.sqlite3'
            store = Store(path, self.doc)
            changed = copy.deepcopy(self.doc)
            changed['sections'][0]['items'].reverse()
            changed['sections'][0]['items'].pop()
            changed['sections'][0]['items'][0]['visible'] = False
            request = {'request_id':'curate', 'base_revision':1, 'experience':changed}
            store.preview(request)
            self.assertEqual(store.state()['experience'], self.doc)
            receipt = store.apply(request)
            self.assertEqual(Store(path, self.doc).state()['experience'], changed)
            self.assertEqual(store.apply(request), receipt)
            store.apply({'request_id':'undo-curation','base_revision':2,'restore_revision':1}, undo=True)
            self.assertEqual(store.state()['experience'], self.doc)

    def test_no_automatic_content_or_arbitrary_route_fields(self):
        for key in ('autoplay','recommendations','feed_url','next_movie'):
            doc = copy.deepcopy(self.doc); doc[key] = True
            with self.assertRaises(Invalid): validate(doc)
        for link in ({'provider':'youtube','content_id':'https://example.com'},
                     {'provider':'netflix','content_id':'12345678','url':'https://example.com'},
                     {'provider':'browser','content_id':'12345678'}):
            doc = copy.deepcopy(self.doc); doc['sections'][0]['items'][0]['playback'] = link
            with self.assertRaises(Invalid): validate(doc)
        self.doc['sections'][0]['items'][0]['playback'] = {'provider':'youtube','content_id':'abcdefghijk'}
        validate(self.doc)

    def test_empty_manual_carousel_is_valid_and_never_repopulated(self):
        self.doc['sections'][0]['items'] = []
        self.assertEqual(validate(self.doc)['sections'][0]['items'], [])
        self.doc['sections'][1]['items'] = []
        with self.assertRaises(Invalid): validate(self.doc)

    def test_movie_posters_use_private_asset_integrity_path_and_old_versions_refuse_movies(self):
        digest = 'a' * 64
        self.doc['sections'][0]['items'][0]['poster'] = digest
        self.assertEqual(artwork_refs(validate(self.doc)), {digest})
        for version in (1,2):
            doc = copy.deepcopy(self.doc); doc['schema_version'] = version
            if version == 1: del doc['collections']
            with self.assertRaises(Invalid): validate(doc)
