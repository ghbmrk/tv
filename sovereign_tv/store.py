"""Atomic local revisions, durable request deduplication, and conflict-safe undo."""
from contextlib import contextmanager
import hashlib
import json
import re
import sqlite3
from .model import Invalid, canonical, fields, validate


class Conflict(ValueError):
    pass


class Store:
    def __init__(self, path, initial):
        validate(initial)
        self.path = str(path)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS revisions (
                    revision INTEGER PRIMARY KEY, document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS receipts (
                    request_id TEXT PRIMARY KEY, digest TEXT NOT NULL, result TEXT NOT NULL);
            ''')
            if not db.execute('SELECT 1 FROM revisions LIMIT 1').fetchone():
                db.execute('INSERT INTO revisions VALUES (1, ?)', (canonical(initial),))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            with db:
                yield db
        finally:
            db.close()

    def state(self):
        with self.connect() as db:
            revision, doc = db.execute('SELECT revision, document FROM revisions ORDER BY revision DESC LIMIT 1').fetchone()
        return {'revision': revision, 'experience': json.loads(doc)}

    def receipt(self, request_id):
        with self.connect() as db:
            row = db.execute('SELECT result FROM receipts WHERE request_id=?', (request_id,)).fetchone()
        return json.loads(row[0]) if row else None

    @staticmethod
    def check_request(request, undo=False):
        fields(request, ('request_id', 'base_revision', 'restore_revision') if undo else
               ('request_id', 'base_revision', 'experience'))
        if not isinstance(request['request_id'], str) or not re.fullmatch(r'[A-Za-z0-9._-]{1,64}', request['request_id']):
            raise Invalid('invalid request ID')
        if type(request['base_revision']) is not int or request['base_revision'] < 1:
            raise Invalid('invalid base revision')
        if undo:
            if type(request['restore_revision']) is not int or not 1 <= request['restore_revision'] < request['base_revision']:
                raise Invalid('restore revision must precede base revision')
        else:
            validate(request['experience'])

    def preview(self, request):
        self.check_request(request)
        state = self.state()
        if state['revision'] != request['base_revision']:
            raise Conflict('state changed; read and rebase')
        return {'base_revision': state['revision'], 'experience': request['experience'],
                'changed_fields': [key for key in request['experience'] if request['experience'][key] != state['experience'][key]],
                'applied': False}

    def apply(self, request, undo=False):
        self.check_request(request, undo)
        digest = hashlib.sha256(canonical({'operation': 'undo' if undo else 'apply', 'request': request}).encode()).hexdigest()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            prior = db.execute('SELECT digest,result FROM receipts WHERE request_id=?', (request['request_id'],)).fetchone()
            if prior:
                if prior[0] != digest:
                    raise Conflict('request ID already used with different arguments')
                return json.loads(prior[1])
            current = db.execute('SELECT MAX(revision) FROM revisions').fetchone()[0]
            if current != request['base_revision']:
                raise Conflict('state changed; read and rebase')
            if undo:
                row = db.execute('SELECT document FROM revisions WHERE revision=?', (request['restore_revision'],)).fetchone()
                if not row:
                    raise Invalid('restore revision not found')
                doc = row[0]
            else:
                doc = canonical(request['experience'])
            revision = current + 1
            db.execute('INSERT INTO revisions VALUES (?, ?)', (revision, doc))
            result = {'request_id': request['request_id'], 'status': 'applied', 'revision': revision,
                      'previous_revision': current, 'document_sha256': hashlib.sha256(doc.encode()).hexdigest()}
            db.execute('INSERT INTO receipts VALUES (?, ?, ?)', (request['request_id'], digest, canonical(result)))
            return result
