"""The SPA fallback serves files of the built frontend and nothing outside it."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from vel.main import create_app


def test_spa_serves_static_files_and_blocks_traversal(tmp_path: Path) -> None:
    static = tmp_path / "dist"
    (static / "assets").mkdir(parents=True)
    (static / "pyodide").mkdir()
    (static / "index.html").write_text("<html>app</html>")
    (static / "pyodide" / "pyodide.asm.wasm").write_bytes(b"\0asm")
    (tmp_path / "secret.txt").write_text("do not serve")
    app = create_app(f"sqlite:///{tmp_path / 'db.sqlite3'}", static_dir=static)
    c = TestClient(app)
    r = c.get("/pyodide/pyodide.asm.wasm")
    assert r.status_code == 200 and r.headers["content-type"] == "application/wasm"
    assert c.get("/projects/abc").text == "<html>app</html>"  # client-side route
    for evil in ("/..%2Fsecret.txt", "/%2e%2e/secret.txt", "/pyodide/..%2F..%2Fsecret.txt"):
        r = c.get(evil)
        assert "do not serve" not in r.text, evil
