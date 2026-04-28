from __future__ import annotations

import unittest

from core.api.app.main import app
from core.api.app.routers.site import index, site_index_path, site_root


class SiteTests(unittest.TestCase):
    def test_site_files_exist(self) -> None:
        self.assertTrue(site_root().exists())
        self.assertTrue(site_index_path().exists())
        self.assertTrue((site_root() / "app.css").exists())
        self.assertTrue((site_root() / "app.js").exists())

    def test_index_route_returns_index_file(self) -> None:
        response = index()
        self.assertEqual(str(response.path), str(site_index_path()))

    def test_index_html_contains_main_flow_controls(self) -> None:
        html = site_index_path().read_text(encoding="utf-8")
        self.assertIn('id="local-import-btn"', html)
        self.assertIn('id="batch-id-input"', html)
        self.assertIn('id="resolve-btn"', html)
        self.assertIn('id="run-query-btn"', html)
        self.assertIn('id="export-btn"', html)
        self.assertIn('id="preview-table"', html)
        self.assertIn('id="results-table"', html)

    def test_app_has_site_routes(self) -> None:
        route_paths = {getattr(route, "path", None) for route in app.routes}
        route_names = {getattr(route, "name", None) for route in app.routes}
        self.assertIn("/", route_paths)
        self.assertIn("static", route_names)


if __name__ == "__main__":
    unittest.main()
