"""cad-viewer 封装的测试。

分两层：
* 逻辑层用**假 HTTP 服务**（不需要 node、不需要真 viewer），覆盖 server_info /
  catalog / step_source_status / verify 的判定与失败分支；
* 真启动层用环境变量 `NSA_VIEWER_LIVE=1` 打开（会 spawn 一个 node 进程，跑完停掉）。
"""

from __future__ import annotations

import json
import os
import sys
import threading
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import viewer  # noqa: E402


# ── 假后端 ────────────────────────────────────────────────────────
class _Fake(BaseHTTPRequestHandler):
    catalog_files: list = []
    step_ok: bool = True

    def log_message(self, *a):        # 静音
        return

    def do_GET(self):                 # noqa: N802
        path = self.path.split("?")[0]
        if path == "/__cad/server":
            body = json.dumps({"app": "cad-viewer", "backend": "local-fs",
                               "viewerVersion": "0.3.5", "pid": 4242})
        elif path == "/__cad/catalog":
            body = json.dumps({"schemaVersion": 4, "entries": [
                {"file": f, "kind": "part"} for f in self.catalog_files]})
        elif path == "/__cad/step-source-status":
            body = json.dumps({"ok": self.step_ok,
                               "sourceKind": "step" if self.step_ok else "",
                               "file": "x.step"})
        else:
            self.send_response(404)
            self.end_headers()
            return
        raw = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


@pytest.fixture()
def fake():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Fake)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    base = "http://127.0.0.1:%d" % srv.server_address[1]
    yield base
    srv.shutdown()
    srv.server_close()


def test_server_info_reads_app_and_backend(fake) -> None:
    info = viewer.server_info(fake)
    assert info and info["app"] == "cad-viewer" and info["backend"] == "local-fs"
    assert info["viewerVersion"] == "0.3.5"


def test_server_info_returns_none_when_down() -> None:
    assert viewer.server_info("http://127.0.0.1:1", timeout=0.5) is None


def test_catalog_and_verify_happy(fake) -> None:
    _Fake.catalog_files = ["a.step", "b.stl"]
    _Fake.step_ok = True
    d = tempfile.mkdtemp(prefix="vw_")
    ver = viewer.verify(fake, d, ["a.step", "b.stl"])
    assert ver["ok"] is True
    assert ver["files_found"] == ["a.step", "b.stl"]
    assert ver["step_source_ok"] == {"a.step": True}
    assert "WebGL" in ver["note"]


def test_verify_reports_missing_file(fake) -> None:
    _Fake.catalog_files = ["a.step"]
    _Fake.step_ok = True
    d = tempfile.mkdtemp(prefix="vw2_")
    ver = viewer.verify(fake, d, ["a.step", "nope.stl"])
    assert ver["ok"] is False
    assert ver["files_missing"] == ["nope.stl"]


def test_verify_reports_step_not_accepted(fake) -> None:
    _Fake.catalog_files = ["a.step"]
    _Fake.step_ok = False
    d = tempfile.mkdtemp(prefix="vw3_")
    ver = viewer.verify(fake, d, ["a.step"])
    assert ver["ok"] is False
    assert ver["step_source_ok"] == {"a.step": False}


def test_verify_when_server_down() -> None:
    d = tempfile.mkdtemp(prefix="vw4_")
    ver = viewer.verify("http://127.0.0.1:1", d, [])
    assert ver["ok"] is False and ver["server_ok"] is False


# ── 链接与启动 ────────────────────────────────────────────────────
def test_review_url_encodes_dir_and_file() -> None:
    url = viewer.review_url("http://127.0.0.1:4178/", "/tmp/a b/中文",
                            "零 件.step")
    assert url.startswith("http://127.0.0.1:4178/?dir=")
    assert "%20" in url and "%E4%B8%AD" in url       # 空格与中文都编码
    assert "&file=" in url


def test_start_reuses_running_server(fake) -> None:
    d = tempfile.mkdtemp(prefix="vw5_")
    port = int(fake.rsplit(":", 1)[1])
    out = viewer.start(d, port=port, wait=3)
    assert out["reused"] is True
    assert out["base"] == fake
    assert out["pid"] == 4242


def test_start_rejects_missing_dir() -> None:
    with pytest.raises(FileNotFoundError):
        viewer.start(os.path.join(tempfile.gettempdir(), "no_such_dir_xyz"), wait=1)


def test_stop_without_pidfile_is_noop() -> None:
    res = viewer.stop(port=59999)
    assert res["stopped"] is False
    assert "pidfile" in res["reason"]


def test_viewer_root_prefers_env() -> None:
    d = tempfile.mkdtemp(prefix="vwroot_")
    os.makedirs(os.path.join(d, "backend"), exist_ok=True)
    with open(os.path.join(d, "backend", "server.mjs"), "w", encoding="utf-8") as fh:
        fh.write("// stub\n")
    old = os.environ.get(viewer.VIEWER_ENV)
    os.environ[viewer.VIEWER_ENV] = d
    try:
        assert os.path.abspath(viewer.viewer_root()) == os.path.abspath(d)
    finally:
        if old is None:
            os.environ.pop(viewer.VIEWER_ENV, None)
        else:
            os.environ[viewer.VIEWER_ENV] = old


# ── 真启动（可选）────────────────────────────────────────────────
@pytest.mark.skipif(os.environ.get("NSA_VIEWER_LIVE") != "1",
                    reason="设 NSA_VIEWER_LIVE=1 才跑真启动")
def test_live_start_verify_stop() -> None:
    d = tempfile.mkdtemp(prefix="vwlive_")
    step = os.path.join(d, "part.step")
    try:
        repo = os.path.dirname(os.path.dirname(HERE))          # 仓库根
        sys.path.insert(0, os.path.join(repo, "kernels", "acad", "src"))
        from acadkit.brep import parts as B
        B.to_step(B.plate(length=100, width=60, thickness=8), step)
    except Exception:                                 # noqa: BLE001
        pytest.skip("缺 cadquery，无法造 STEP")

    out = viewer.start(d, port=4189, wait=40)
    try:
        ver = viewer.verify(out["base"], d, ["part.step"])
        assert ver["server_ok"] is True
        assert ver["step_source_ok"] == {"part.step": True}, ver
        assert ver["ok"] is True, ver
    finally:
        viewer.stop(port=4189)
