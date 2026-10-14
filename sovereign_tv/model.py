"""Version-one portable experience format. Data only: no code or remote URLs."""
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
    fields(doc, ('schema_version', 'title', 'theme', 'sections', 'settings'))
    if type(doc['schema_version']) is not int or doc['schema_version'] != 1:
        raise Invalid('unsupported schema version')
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
    settings = doc['settings']
    fields(settings, ('text_scale', 'artwork_interval_seconds'))
    scale = settings['text_scale']
    if type(scale) not in (int, float) or not 0.8 <= scale <= 1.6:
        raise Invalid('text scale outside 0.8–1.6')
    interval = settings['artwork_interval_seconds']
    if type(interval) is not int or not 30 <= interval <= 86400:
        raise Invalid('artwork interval outside 30–86400 seconds')
    return doc


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
