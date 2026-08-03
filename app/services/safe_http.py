"""Restricted HTTP helpers for downloading untrusted image URLs."""

import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import requests
from PIL import Image
from io import BytesIO


MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_REDIRECTS = 3
ALLOWED_PORTS = {None, 80, 443}
IMAGE_MIME_TYPES = {
    'JPEG': 'image/jpeg',
    'PNG': 'image/png',
    'GIF': 'image/gif',
    'WEBP': 'image/webp',
}


class UnsafeRemoteUrl(ValueError):
    """Raised when a URL could reach a local or otherwise unsafe address."""


def _is_public_address(address):
    ip = ipaddress.ip_address(address)
    return (
        ip.is_global
        and not ip.is_private
        and not ip.is_loopback
        and not ip.is_link_local
        and not ip.is_multicast
        and not ip.is_reserved
        and not ip.is_unspecified
    )


def validate_public_http_url(url):
    """Validate an HTTP(S) URL and ensure every resolved address is public."""
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        raise UnsafeRemoteUrl('Only HTTP and HTTPS image URLs are allowed.')
    if not parsed.hostname or parsed.username or parsed.password:
        raise UnsafeRemoteUrl('The image URL host is invalid.')

    try:
        port = parsed.port
    except ValueError as exc:
        raise UnsafeRemoteUrl('The image URL port is invalid.') from exc
    if port not in ALLOWED_PORTS:
        raise UnsafeRemoteUrl('Only standard HTTP and HTTPS ports are allowed.')

    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(
                parsed.hostname,
                port or (443 if parsed.scheme == 'https' else 80),
                type=socket.SOCK_STREAM,
            )
        }
    except socket.gaierror as exc:
        raise UnsafeRemoteUrl('The image URL host could not be resolved.') from exc

    if not addresses or any(not _is_public_address(address) for address in addresses):
        raise UnsafeRemoteUrl('Local and private network image URLs are not allowed.')
    return url


def fetch_public_image(url, *, timeout=10, max_bytes=MAX_IMAGE_BYTES):
    """Download a bounded public image while validating every redirect."""
    headers = {
        'User-Agent': (
            'ComicBookManager/1.0 '
            '(https://github.com/Crench88/ComicbookMgr) Python/3.x'
        ),
    }
    current_url = url

    for redirect_count in range(MAX_REDIRECTS + 1):
        validate_public_http_url(current_url)
        response = requests.get(
            current_url,
            headers=headers,
            timeout=timeout,
            stream=True,
            allow_redirects=False,
        )

        if response.is_redirect or response.is_permanent_redirect:
            response.close()
            if redirect_count >= MAX_REDIRECTS:
                raise requests.TooManyRedirects('Too many image redirects.')
            location = response.headers.get('location')
            if not location:
                raise requests.RequestException('Image redirect had no destination.')
            current_url = urljoin(current_url, location)
            continue

        response.raise_for_status()
        content_length = response.headers.get('content-length')
        if content_length:
            try:
                if int(content_length) > max_bytes:
                    response.close()
                    raise requests.RequestException('The remote image is too large.')
            except ValueError:
                pass

        chunks = []
        total = 0
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            total += len(chunk)
            if total > max_bytes:
                response.close()
                raise requests.RequestException('The remote image is too large.')
            chunks.append(chunk)
        response.close()
        image_data = b''.join(chunks)

        # Some image CDNs return application/octet-stream or another
        # inaccurate Content-Type. Trust verified image bytes, not the header.
        try:
            with Image.open(BytesIO(image_data)) as image:
                image.verify()
                content_type = IMAGE_MIME_TYPES.get((image.format or '').upper())
        except (Image.UnidentifiedImageError, Image.DecompressionBombError, OSError) as exc:
            raise requests.RequestException(
                'The remote URL did not return a supported image.'
            ) from exc
        if not content_type:
            raise requests.RequestException(
                'The remote URL did not return a supported image.'
            )
        return image_data, content_type

    raise requests.TooManyRedirects('Too many image redirects.')
