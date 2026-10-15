"""Versioned portable experience format. Data only: no code or remote URLs."""
import json
import re


class Invalid(ValueError):
    pass


def fields(value, required):
    if not isinstance(value, dict) or set(value) != set(required):
        raise Invalid('unexpected or missing fields')


def label(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 120 or any(ord(c) < 32 for c in value):
        raise Invalid('labels must contain 1–120 printable characters')


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', value):
        raise Invalid('invalid identifier')


def validate(doc):
    version = doc.get('schema_version') if isinstance(doc, dict) else None
    if type(version) is not int or version not in (1, 2):
        raise Invalid('unsupported schema version')
    fields(doc, ('schema_version', 'title', 'theme', 'sections', 'settings') + (('collections',) if version == 2 else ()))
    label(doc['title'])
    if doc['theme'] not in ('night', 'warm', 'light'):
        raise Invalid('unsupported theme')
    sections = doc['sections']
    if not isinstance(sections, list) or not 1 <= len(sections) <= 12:
        raise Invalid('1–12 sections required')
    ids = set()
    count = 0
    for section in sections:
        fields(section, ('id', 'title', 'layout', 'items'))
        identifier(section['id'])
        label(section['title'])
        if section['id'] in ids:
            raise Invalid('duplicate identifier')
        ids.add(section['id'])
        if section['layout'] not in ('row', 'grid'):
            raise Invalid('unsupported layout')
        if not isinstance(section['items'], list) or not 1 <= len(section['items']) <= 24:
            raise Invalid('1–24 items per section required')
        for item in section['items']:
            fields(item, ('id', 'title', 'kind', 'target', 'visible'))
            identifier(item['id'])
            identifier(item['target'])
            label(item['title'])
            if item['id'] in ids:
                raise Invalid('duplicate identifier')
            ids.add(item['id'])
            if item['kind'] not in ('app', 'collection') or type(item['visible']) is not bool:
                raise Invalid('unsupported item')
            count += int(item['visible'])
    if not count:
        raise Invalid('at least one visible item required')
    if version == 2:
        collections = doc['collections']
        if not isinstance(collections, list) or len(collections) > 12:
            raise Invalid('at most 12 collections allowed')
        collection_ids = set()
        entries = 0
        for collection in collections:
            fields(collection, ('id', 'title', 'items'))
            identifier(collection['id'])
            label(collection['title'])
            if collection['id'] in collection_ids:
                raise Invalid('duplicate collection')
            collection_ids.add(collection['id'])
            if not isinstance(collection['items'], list) or len(collection['items']) > 48:
                raise Invalid('at most 48 entries per collection allowed')
            item_ids = set()
            for item in collection['items']:
                fields(item, ('id', 'title', 'kind', 'target', 'visible'))
                identifier(item['id'])
                label(item['title'])
                if item['id'] in item_ids or type(item['visible']) is not bool:
                    raise Invalid('invalid collection entry')
                item_ids.add(item['id'])
                if item['kind'] == 'app':
                    identifier(item['target'])
                elif item['kind'] == 'artwork':
                    if not isinstance(item['target'], str) or not re.fullmatch(r'[a-f0-9]{64}', item['target']):
                        raise Invalid('artwork must reference a SHA-256 asset')
                else:
                    raise Invalid('collections contain only apps or artwork')
                entries += 1
        if entries > 256 or any(item['target'] not in collection_ids for section in sections
                               for item in section['items'] if item['kind'] == 'collection'):
            raise Invalid('collection limit or unresolved reference')
    settings = doc['settings']
    fields(settings, ('text_scale', 'artwork_interval_seconds'))
    scale = settings['text_scale']
    if type(scale) not in (int, float) or not 0.8 <= scale <= 1.6:
        raise Invalid('text scale outside 0.8–1.6')
    interval = settings['artwork_interval_seconds']
    if type(interval) is not int or not 30 <= interval <= 86400:
        raise Invalid('artwork interval outside 30–86400 seconds')
    if len(canonical(doc).encode()) > 65536:
        raise Invalid('experience exceeds 64 KiB')
    return doc


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def artwork_refs(doc):
    return {item['target'] for collection in doc.get('collections', [])
            for item in collection['items'] if item['kind'] == 'artwork'}
