"""Bounded, owner-only previews. Untrusted documents never render as browser HTML."""

import csv
import codecs
import io
import os
import zipfile
from pathlib import PurePath

import httpx
from fastapi import HTTPException, Response
from fastapi.responses import JSONResponse

MAX_SOURCE_BYTES = 1024 * 1024
MAX_PDF_BYTES = 25 * 1024 * 1024
MAX_CSV_ROWS = 200
MAX_CSV_COLUMNS = 50
OFFICE_PARTS = {".docx": "word/document.xml", ".xlsx": "xl/workbook.xml",
                ".pptx": "ppt/presentation.xml"}
TEXT_EXTENSIONS = {
    ".txt", ".text", ".log", ".md", ".markdown", ".py", ".go",
    ".java", ".js", ".jsx", ".ts", ".tsx", ".html", ".htm",
    ".css", ".json", ".xml", ".yaml", ".yml", ".sh", ".sql",
}
SAFE_HEADERS = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
                "Content-Disposition": "attachment", "Content-Security-Policy": "sandbox"}


def _safe_office(content: bytes, extension: str) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            parts = archive.infolist()
            names = {part.filename for part in parts}
            return (len(parts) <= 1000 and sum(part.file_size for part in parts) <= 80 * 1024 * 1024
                    and "[Content_Types].xml" in names and OFFICE_PARTS[extension] in names
                    and not any("vbaProject.bin" in name for name in names))
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile):
        return False


async def _office_pdf(content: bytes, filename: str) -> bytes:
    converter = os.getenv("PREVIEW_CONVERTER_URL", "http://127.0.0.1:3001").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(35.0, connect=3.0)) as client:
            async with client.stream("POST", f"{converter}/forms/libreoffice/convert",
                                     files={"files": (filename, content, "application/octet-stream")}) as result:
                if result.status_code == 400:
                    raise HTTPException(415, "This Office file cannot be converted")
                if result.status_code != 200:
                    raise HTTPException(502, "Document preview conversion failed")
                chunks = []
                size = 0
                async for chunk in result.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_PDF_BYTES:
                        raise HTTPException(413, "Converted preview is too large")
                    chunks.append(chunk)
    except httpx.TimeoutException as exc:
        raise HTTPException(503, "Document preview timed out") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(503, "Document preview service is unavailable") from exc
    pdf = b"".join(chunks)
    if not pdf.startswith(b"%PDF-"):
        raise HTTPException(502, "Document preview service returned an invalid PDF")
    return pdf


async def preview_response(filename: str, content: bytes) -> Response:
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(413, "File is too large to preview")
    extension = PurePath(filename).suffix.lower()
    if extension in OFFICE_PARTS:
        if not _safe_office(content, extension):
            raise HTTPException(415, "This Office file cannot be previewed")
        pdf = await _office_pdf(content, filename)
        return Response(pdf, media_type="application/pdf", headers=SAFE_HEADERS)

    if extension == ".pdf":
        if not content.startswith(b"%PDF-") or len(content) > MAX_PDF_BYTES:
            raise HTTPException(415, "This PDF cannot be previewed")
        return Response(content, media_type="application/pdf", headers=SAFE_HEADERS)

    image_types = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                   ".gif": "image/gif", ".webp": "image/webp"}
    if extension in image_types:
        valid = (extension == ".png" and content.startswith(b"\x89PNG\r\n\x1a\n")
                 or extension in (".jpg", ".jpeg") and content.startswith(b"\xff\xd8\xff")
                 or extension == ".gif" and content[:6] in (b"GIF87a", b"GIF89a")
                 or extension == ".webp" and content[:4] == b"RIFF" and content[8:12] == b"WEBP")
        if not valid:
            raise HTTPException(415, "This image cannot be previewed")
        return Response(content, media_type=image_types[extension], headers=SAFE_HEADERS)

    if extension == ".csv" or extension in TEXT_EXTENSIONS:
        preview = content[:MAX_SOURCE_BYTES]
        try:
            decoded = (content.decode("utf-8-sig") if extension == ".csv" else
                       codecs.getincrementaldecoder("utf-8-sig")("strict").decode(
                           preview, final=len(content) <= MAX_SOURCE_BYTES))
        except UnicodeDecodeError:
            raise HTTPException(415, "This text file is not UTF-8") from None
        if "\x00" in decoded:
            raise HTTPException(415, "This text file is not UTF-8")
        if extension == ".csv":
            try:
                reader = csv.reader(io.StringIO(decoded, newline=""), strict=True)
                rows = []
                used = 0
                for index, row in enumerate(reader):
                    row_size = sum(len(cell.encode("utf-8")) for cell in row)
                    if index >= MAX_CSV_ROWS or len(row) > MAX_CSV_COLUMNS or used + row_size > MAX_SOURCE_BYTES:
                        return JSONResponse({"kind": "table", "rows": rows, "truncated": True},
                                            headers=SAFE_HEADERS)
                    rows.append(row)
                    used += row_size
            except csv.Error:
                raise HTTPException(415, "This CSV cannot be previewed") from None
            return JSONResponse({"kind": "table", "rows": rows, "truncated": False},
                                headers=SAFE_HEADERS)
        return JSONResponse({"kind": "markdown" if extension in (".md", ".markdown") else "text",
                             "text": decoded, "truncated": len(content) > MAX_SOURCE_BYTES},
                            headers=SAFE_HEADERS)

    raise HTTPException(415, "Preview is unavailable for this file type")
