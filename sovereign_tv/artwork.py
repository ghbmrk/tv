"""Private immutable PNG assets. No URLs, executable formats, or automatic deletion."""
import hashlib
import os
from pathlib import Path
import re
import struct
import tempfile
import threading
import zlib
from .model import Invalid

MAX_IMAGE_BYTES = 8 * 1024**2
MAX_PIXELS = 4096 * 2160
MAX_STORE_BYTES = 128 * 1024**2
MAX_EXPERIENCE_ASSET_BYTES = 32 * 1024**2


def png_info(data):
    if not 45 <= len(data) <= MAX_IMAGE_BYTES or data[:8] != b'\x89PNG\r\n\x1a\n':
        raise Invalid('PNG required, at most 8 MiB')
    pos, width, height, channels, compressed = 8, 0, 0, 0, bytearray()
    seen_idat = ended_idat = False
    while pos < len(data):
        if pos + 12 > len(data):
            raise Invalid('truncated PNG')
        length = int.from_bytes(data[pos:pos + 4], 'big')
        kind = data[pos + 4:pos + 8]
        end = pos + 12 + length
        if end > len(data) or not re.fullmatch(b'[A-Za-z]{4}', kind):
            raise Invalid('invalid PNG chunk')
        payload = data[pos + 8:pos + 8 + length]
        if zlib.crc32(kind + payload) != int.from_bytes(data[end - 4:end], 'big'):
            raise Invalid('PNG CRC mismatch')
        if pos == 8 and kind != b'IHDR':
            raise Invalid('PNG header must be first')
        if kind == b'IHDR':
            if pos != 8 or length != 13:
                raise Invalid('invalid PNG header')
            width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', payload)
            if not (1 <= width <= 8192 and 1 <= height <= 8192 and width * height <= MAX_PIXELS
                    and depth == 8 and color in (2, 6) and compression == filtering == interlace == 0):
                raise Invalid('use noninterlaced 8-bit RGB/RGBA PNG, at most 4096×2160 pixels in area')
            channels = 3 if color == 2 else 4
        elif kind == b'IDAT':
            if ended_idat:
                raise Invalid('nonconsecutive PNG data')
            seen_idat = True
            compressed.extend(payload)
        else:
            if seen_idat:
                ended_idat = True
            if kind == b'IEND':
                if length != 0 or end != len(data) or not seen_idat:
                    raise Invalid('invalid PNG end')
                break
            # Deliberately narrow profile: excludes APNG, text, EXIF and compressed metadata.
            if kind not in (b'sRGB', b'gAMA', b'cHRM', b'pHYs') or seen_idat:
                raise Invalid('unsupported PNG metadata; export a plain RGB/RGBA PNG')
            if length != {b'sRGB': 1, b'gAMA': 4, b'cHRM': 32, b'pHYs': 9}[kind]:
                raise Invalid('invalid PNG metadata length')
        pos = end
    else:
        raise Invalid('PNG end missing')
    stride = 1 + width * channels
    expected, count = height * stride, 0
    decoder = zlib.decompressobj()
    remaining = bytes(compressed)
    try:
        while remaining:
            output = decoder.decompress(remaining, min(65536, expected + 1 - count))
            for index in range((-count) % stride, len(output), stride):
                if output[index] > 4:
                    raise Invalid('invalid PNG scanline filter')
            count += len(output)
            if count > expected or decoder.unused_data:
                raise Invalid('PNG decompression exceeds declared image')
            remaining = decoder.unconsumed_tail
        if count != expected or not decoder.eof:
            raise Invalid('incomplete PNG image')
    except zlib.error as error:
        raise Invalid('invalid PNG compression') from error
    return {'width': width, 'height': height, 'bytes': len(data), 'media_type': 'image/png'}


class ArtworkStore:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.Lock()

    def path(self, digest):
        if not isinstance(digest, str) or not re.fullmatch(r'[a-f0-9]{64}', digest):
            raise Invalid('invalid asset ID')
        return self.directory / (digest + '.png')

    def read(self, digest):
        path = self.path(digest)
        with path.open('rb') as stream:
            data = stream.read(MAX_IMAGE_BYTES + 1)
        if hashlib.sha256(data).hexdigest() != digest:
            raise Invalid('asset integrity mismatch')
        png_info(data)
        return data

    def require(self, references):
        total = 0
        for digest in references:
            total += len(self.read(digest))
            if total > MAX_EXPERIENCE_ASSET_BYTES:
                raise Invalid('one experience may reference at most 32 MiB of artwork')

    def put(self, digest, data):
        info = png_info(data)
        path = self.path(digest)
        if hashlib.sha256(data).hexdigest() != digest:
            raise Invalid('asset hash mismatch')
        with self.lock:
            if path.exists():
                self.read(digest)
            else:
                if sum(p.stat().st_size for p in self.directory.glob('*.png')) + len(data) > MAX_STORE_BYTES:
                    raise Invalid('artwork storage full; no saved artwork was deleted')
                fd, temporary = tempfile.mkstemp(prefix='.upload-', dir=self.directory)
                try:
                    with os.fdopen(fd, 'wb') as stream:
                        stream.write(data)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(temporary, path)
                finally:
                    if os.path.exists(temporary):
                        os.unlink(temporary)
            fd = os.open(self.directory, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        return dict(info, id=digest)
