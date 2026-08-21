"""Media proxy views.

Serve files from the private S3 bucket with forced Content-Types so that
browsers render them (SVG requires `image/svg+xml`). URLs are stable and
non-expiring; the bucket stays private (no permanent public URLs).
"""
from mimetypes import guess_type

from django.core.files.storage import default_storage
from django.http import FileResponse, Http404
from django.views import View

ALLOWED_MEDIA_PREFIXES = ('logos/',)

SVG_CONTENT_TYPE = 'image/svg+xml'


class MediaFileView(View):
    """Stream a media file from the default (S3) storage.

    Only paths under ALLOWED_MEDIA_PREFIXES are served. The Content-Type is
    forced by file extension (SVG in particular), fixing logos that T3
    serves as `application/xml` and that browsers refuse to render.
    """

    def get(self, request, file_path):
        name = self._sanitize(file_path)
        if name is None:
            raise Http404
        try:
            media_file = default_storage.open(name, 'rb')
        except (FileNotFoundError, OSError):
            raise Http404
        response = FileResponse(media_file, content_type=self._content_type(name))
        response['Cache-Control'] = 'public, max-age=31536000, immutable'
        return response

    @staticmethod
    def _sanitize(file_path):
        """Reject traversal/absolute paths and out-of-whitelist prefixes."""
        parts = [p for p in file_path.split('/') if p not in ('', '.', '..')]
        if not parts:
            return None
        name = '/'.join(parts)
        if not name.startswith(ALLOWED_MEDIA_PREFIXES):
            return None
        return name

    @staticmethod
    def _content_type(name):
        if name.lower().endswith('.svg'):
            return SVG_CONTENT_TYPE
        return guess_type(name)[0] or 'application/octet-stream'
