"""PypdfText: the `PdfText` port over `pypdf` (P10.19). API only.

`pypdf` is pinned in `services/ai/requirements-api.txt`, never in `requirements.txt`, so `predict.py` and
the offline install never need it; it is imported inside `extract`. Only the text layer is read: a scanned
PDF gives no text (the use case then refuses it), and nothing in the file is ever executed or rendered.
"""

from __future__ import annotations

import importlib.util
import io
import logging

from campuspulse_ai.domain.errors import InvalidInput

log = logging.getLogger(__name__)


class PypdfText:
    @staticmethod
    def available() -> bool:
        """True when `pypdf` is installed (the API image); the composition root wires PDFs only then."""
        return importlib.util.find_spec("pypdf") is not None

    def extract(self, data: bytes, max_pages: int) -> str:
        from pypdf import PdfReader  # API only (module docstring)

        try:
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted and not reader.decrypt(""):
                raise InvalidInput("the PDF is password-protected; it cannot be read")
            if len(reader.pages) > max_pages:
                raise InvalidInput(f"the PDF has more than {max_pages} pages")
            pages = [page.extract_text() or "" for page in reader.pages]
        except InvalidInput:
            raise
        except Exception as exc:  # pypdf raises PdfReadError, ValueError, KeyError, ... on a broken file
            log.info("knowledge: unreadable PDF (%s)", type(exc).__name__)
            raise InvalidInput("the PDF could not be read; it may be damaged") from None
        return "\n\n".join(pages)
