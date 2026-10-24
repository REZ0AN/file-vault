"""Preview format validation and converter boundaries."""

import asyncio
import io
import unittest
import zipfile
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.preview import preview_response


def office_file(part: str) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr(part, "<document/>")
    return output.getvalue()


class PreviewTest(unittest.TestCase):
    def render(self, name: str, content: bytes):
        return asyncio.run(preview_response(name, content))

    def test_source_html_is_json_not_executable_html(self):
        response = self.render("page.html", b"<script>alert(1)</script>")
        self.assertEqual(response.media_type, "application/json")
        self.assertIn(b"<script>alert(1)</script>", response.body)
        self.assertEqual(response.headers["cache-control"], "private, no-store")

    def test_csv_is_bounded_and_image_is_signature_checked(self):
        response = self.render("sheet.csv", b"name,value\nhello,=1+1\n")
        self.assertIn(b'"kind":"table"', response.body)
        self.assertIn(b"=1+1", response.body)
        with self.assertRaises(HTTPException) as problem:
            self.render("fake.png", b"<svg onload=alert(1)>")
        self.assertEqual(problem.exception.status_code, 415)
        with self.assertRaises(HTTPException):
            self.render("drawing.svg", b"<svg/>")

    def test_office_requires_valid_package_and_converter_pdf(self):
        with self.assertRaises(HTTPException):
            self.render("bad.docx", b"not a zip")
        converted = AsyncMock(return_value=b"%PDF-1.7\nconverted")
        with patch("app.preview._office_pdf", converted):
            response = self.render("good.docx", office_file("word/document.xml"))
        self.assertEqual(response.media_type, "application/pdf")
        self.assertEqual(response.body, b"%PDF-1.7\nconverted")
        with self.assertRaises(HTTPException):
            self.render("macro.docm", office_file("word/document.xml"))

    def test_binary_text_and_large_files_rejected(self):
        for name, body in (("bad.txt", b"a\x00b"), ("bad.pdf", b"not pdf"),
                           ("big.txt", b"x" * (5 * 1024 * 1024 + 1))):
            with self.subTest(name=name), self.assertRaises(HTTPException):
                self.render(name, body)
