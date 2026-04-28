from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.web.settings")

import django
from django.test import Client

django.setup()

from core.api.app.main import app
from django.conf import settings


class SiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.client = Client()

    def test_site_files_exist(self) -> None:
        template_path = Path(settings.TEMPLATES[0]["DIRS"][0]) / "web" / "index.html"
        static_root = settings.STATICFILES_DIRS[0] / "web"
        self.assertTrue(template_path.exists())
        self.assertTrue((static_root / "app.css").exists())
        self.assertTrue((static_root / "app.js").exists())

    def test_index_route_renders_django_page(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertIn("Budget Analytics", html)
        self.assertIn(settings.BUDGET_API_BASE_URL, html)

    def test_index_html_contains_main_flow_controls(self) -> None:
        template_path = Path(settings.TEMPLATES[0]["DIRS"][0]) / "web" / "index.html"
        html = template_path.read_text(encoding="utf-8")
        self.assertIn('id="import-dropzone"', html)
        self.assertIn('id="choose-archive-btn"', html)
        self.assertIn('id="choose-folder-btn"', html)
        self.assertIn('id="run-query-btn"', html)
        self.assertIn('id="export-btn"', html)
        self.assertIn('id="preview-table"', html)
        self.assertIn('id="results-table"', html)
        self.assertNotIn('id="local-import-btn"', html)
        self.assertNotIn('id="resolve-btn"', html)

    def test_fastapi_app_exposes_only_api_and_system_routes(self) -> None:
        route_paths = {getattr(route, "path", None) for route in app.routes}
        route_names = {getattr(route, "name", None) for route in app.routes if getattr(route, "name", None)}
        self.assertNotIn("/", route_paths)
        self.assertNotIn("static", route_names)
        self.assertIn("/health", route_paths)
        self.assertIn("/api/v1/imports/default", route_paths)
        self.assertIn("/api/v1/imports/archive", route_paths)
        self.assertIn("/api/v1/analytics/query", route_paths)


if __name__ == "__main__":
    unittest.main()
