"""Export OpenAPI + JSON Schema into engine/docs/."""

from __future__ import annotations

import json
from pathlib import Path

from app.main import create_app

DOCS = Path(__file__).resolve().parent.parent / "docs"


def export() -> Path:
    DOCS.mkdir(parents=True, exist_ok=True)
    app = create_app()
    openapi = app.openapi()
    openapi["servers"] = [
        {"url": "http://127.0.0.1:8000", "description": "Local engine"},
    ]
    (DOCS / "openapi.json").write_text(
        json.dumps(openapi, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    from fastapi.testclient import TestClient

    client = TestClient(app)
    contracts = client.get("/v1/contracts").json()
    (DOCS / "contracts.json").write_text(
        json.dumps(contracts, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    spec_js = json.dumps(openapi, ensure_ascii=False)
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>Policy rehearsal engine — API</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css"/>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    const spec = {spec_js};
    window.ui = SwaggerUIBundle({{
      spec: spec,
      dom_id: "#swagger-ui",
      deepLinking: true,
    }});
  </script>
</body>
</html>
"""
    (DOCS / "swagger.html").write_text(html, encoding="utf-8")
    zip_path = DOCS / "policy-engine-api-docs.zip"
    import zipfile

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in ("API.md", "openapi.json", "contracts.json", "swagger.html"):
            archive.write(DOCS / name, arcname=name)
    return DOCS


if __name__ == "__main__":
    print(export())
