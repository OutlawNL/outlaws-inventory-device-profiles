"""Bounded downloads for firmware document discovery and parsing."""
import time


def get(client, url, *, max_bytes=32 * 1024 * 1024, timeout=30, **kwargs):
    started = time.monotonic()
    response = client.get(url, timeout=timeout, stream=True, **kwargs)
    try:
        response.raise_for_status()
        length = response.headers.get('Content-Length')
        if length and int(length) > max_bytes:
            raise ValueError('Firmware document exceeds the download limit.')
        chunks = []
        size = 0
        for chunk in response.iter_content(chunk_size=65536):
            if time.monotonic() - started > timeout:
                raise TimeoutError('Firmware document download exceeded its time limit.')
            size += len(chunk)
            if size > max_bytes:
                raise ValueError('Firmware document exceeds the download limit.')
            chunks.append(chunk)
        response._content = b''.join(chunks)
        response._content_consumed = True
        return response
    finally:
        response.close()
