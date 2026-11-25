"""Read-only viewer scoped to one project or global across multiple projects."""
from __future__ import annotations

import base64
import binascii
import hashlib
import uuid
import threading
import gzip
import os
import http.server
import json
import mimetypes
import urllib.parse
import urllib.request
from pathlib import Path

from Tools._resolve import resolve_asset
from Tools.project_manifest import inside, load_project, identifier

VIEWER_DIR = Path(__file__).resolve().parent / "viewer"


_REVISION_FILES = ("viewer_server.py", "model_viewer.py", "_resolve.py", "project_manifest.py")


def backend_revision():
    """Revision of every backend module that shapes what a viewer process serves or decides."""
    digest = hashlib.sha256()
    base = Path(__file__).resolve().parent
    for name in _REVISION_FILES:
        try:
            digest.update(name.encode() + b"|" + (base / name).read_bytes())
        except OSError:
            digest.update(name.encode() + b"|missing")
    return digest.hexdigest()[:16]


_RUNTIME_VERSION = None


def runtime_version():
    global _RUNTIME_VERSION
    if _RUNTIME_VERSION is None:
        try:
            data = json.loads((VIEWER_DIR / "runtime-version.json").read_text(encoding="utf-8-sig"))
            _RUNTIME_VERSION = str(data["version"])
        except (OSError, ValueError, KeyError, TypeError):
            _RUNTIME_VERSION = "2.0.0"
    return _RUNTIME_VERSION


GLOBAL_PREFERRED_PORT = 8765
GLOBAL_FALLBACK_PORTS = 20


def texture_index(text, count=None):
    """A texture URL index that is not a non-negative integer names nothing: 404, not a validation failure."""
    try:
        index = int(text)
    except (TypeError, ValueError):
        raise KeyError(f"Texture '{text}' not found") from None
    if index < 0:
        raise IndexError(f"Texture '{text}' not found")
    return index


def decode_data_uri(source):
    try:
        header, payload = source.split(",", 1)
    except ValueError:
        raise binascii.Error("Malformed embedded texture data URI") from None
    return base64.b64decode(payload, validate=True), header[5:].split(";")[0]


class _ExclusiveServer(http.server.ThreadingHTTPServer):
    # SO_REUSEADDR lets a second server bind a port already in use on Windows, so two viewers started at once
    # (parallel captures) would share one port and answer each other's requests; a busy port must fail instead.
    allow_reuse_address = False


def workspace_id(path):
    return hashlib.sha256(str(Path(path).resolve()).lower().encode()).hexdigest()


def stamp(path):
    try:
        stat = path.stat()
        return [str(stat.st_mtime_ns), stat.st_size]
    except OSError:
        return None


def probe_health(host: str = "127.0.0.1", port: int = 8765, timeout: float = 1.0) -> dict | None:
    """Check if an active noct3d-viewer is already running on host:port."""
    try:
        url = f"http://{host}:{port}/api/health"
        req = urllib.request.Request(url, headers={"User-Agent": "noct3d-viewer-probe"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                if isinstance(data, dict) and data.get("app") == "noct3d-viewer":
                    return data
    except Exception:
        pass
    return None


def is_server_running(host: str = "127.0.0.1", port: int = 8765, timeout: float = 1.0) -> bool:
    """Return True if a noct3d-viewer server is answering on host:port."""
    return probe_health(host=host, port=port, timeout=timeout) is not None


class ModelViewerServer:
    def __init__(self, host="127.0.0.1", port=None, *, project=None, model=None, allowed_files=(), projects_root=None):
        self.host = host
        self.instance_id = str(uuid.uuid4())
        self.server_revision = backend_revision()
        self._texture_metadata = {}
        self._project_metadata = {}
        self._project_summaries = {}
        self._metadata_lock = threading.RLock()
        self.projects_root = Path(projects_root).resolve() if projects_root else None
        self.project = Path(project).resolve() if project else None
        self.direct_model = Path(model).resolve() if model else None
        self.allowed_files = {Path(path).resolve() for path in allowed_files if path is not None}
        if self.direct_model:
            self.allowed_files.add(self.direct_model)

        if port is None:
            port = GLOBAL_PREFERRED_PORT if self.projects_root is not None else 8080
            self._port_explicit = False
        else:
            self._port_explicit = True

        owner = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def response(self, payload, mime, code=200):
                compressed = mime.startswith("application/json") and len(payload) > 4096 and "gzip" in self.headers.get("Accept-Encoding", "")
                if compressed:
                    payload = gzip.compress(payload, compresslevel=1)
                self.send_response(code)
                if compressed:
                    self.send_header("Content-Encoding", "gzip")
                    self.send_header("Vary", "Accept-Encoding")
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(payload)

            def redirect(self, location, code=302):
                self.send_response(code)
                self.send_header("Location", location)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_HEAD(self):
                self.do_GET()

            def host_allowed(self):
                """Only loopback names on this server's port: a rebinding page answers to its own hostname."""
                host = (self.headers.get("Host") or "").strip()
                if host.startswith("["):
                    name, _, rest = host[1:].partition("]")
                    port_text = rest[1:] if rest.startswith(":") else ""
                    if rest and not rest.startswith(":"):
                        return False
                else:
                    name, _, port_text = host.partition(":")
                if name.lower() not in ("127.0.0.1", "localhost", "::1"):
                    return False
                return not port_text or port_text == str(self.server.server_address[1])

            def do_GET(self):
                parsed = urllib.parse.urlsplit(self.path)
                route = urllib.parse.unquote(parsed.path)
                try:
                    if not self.host_allowed():
                        self.response(json.dumps({"error": "Host not allowed"}).encode(), "application/json", 403)
                        return
                    if route in ("/", "/index.html", "/viewer"):
                        self.response((VIEWER_DIR / "index.html").read_bytes(), "text/html; charset=utf-8")
                    elif route.startswith(("/vendor/", "/js/", "/css/")):
                        path = inside(VIEWER_DIR, route.lstrip("/"))
                        mime = "text/css; charset=utf-8" if path.suffix.lower() == ".css" else "application/javascript; charset=utf-8"
                        self.response(path.read_bytes(), mime)
                    elif route.startswith("/lib/"):
                        owner.serve_lib(self, route)
                    elif route == "/api/health":
                        mode = "global" if owner.projects_root is not None else "project"
                        self.response(json.dumps({"app": "noct3d-viewer", "mode": mode, "protocolVersion": 2, "runtimeVersion": runtime_version(), "serverRevision": owner.server_revision, "processId": os.getpid(), "instanceId": owner.instance_id, "workspaceId": workspace_id(owner.projects_root or owner.project or (owner.direct_model.parent if owner.direct_model else VIEWER_DIR)), "scope": str(owner.project) if owner.project else None}).encode(), "application/json; charset=utf-8")
                    elif route == "/api/catalog":
                        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
                        project_name = query.get("project", [None])[0]
                        project_dir = owner.resolve_project_dir(project_name) if project_name else owner.project
                        if project_dir or owner.direct_model:
                            cat = owner.catalog(project_dir=project_dir, project_name=project_name, detail_asset=query.get("asset", [None])[0])
                        else:
                            cat = {"assets": [], "glbs": [], "sandboxes": []}
                        # A selected project must not walk every other project's export tree.
                        cat["projects"] = owner.list_projects() if not project_name else []
                        cat["schemaVersion"] = 2
                        sandbox = query.get("sandbox", [None])[0]
                        if sandbox and project_dir:
                            directory = inside(project_dir / "sandboxes", sandbox)
                            cat["compositionRevision"] = [[str(path.relative_to(directory)), stamp(path)] for path in sorted(directory.rglob("*")) if path.is_file() and path.suffix in (".html", ".css", ".js") and "node_modules" not in path.relative_to(directory).parts]
                        cat["revision"] = hashlib.sha256(json.dumps(cat, sort_keys=True).encode()).hexdigest()
                        self.response(json.dumps(cat, ensure_ascii=False).encode(), "application/json; charset=utf-8")
                    elif route.startswith("/api/p/"):
                        owner.handle_project_api(self, route, parsed.query)
                    elif route.startswith("/api/assets/"):
                        segments = route.split("/")[3:]
                        asset_id = segments[0]
                        if owner.project and (owner.project / "project.json").is_file():
                            data = owner.project_data(owner.project)
                            record = data.get("assets", {}).get(asset_id)
                            if not record:
                                raise KeyError(f"Asset '{asset_id}' not found in project")
                            model_path = inside(owner.project, record.get("model", ""))
                            if segments[1:] == ["model"]:
                                self.response(json.dumps(owner.model_data(model_path, asset_id)).encode(), "application/json; charset=utf-8")
                            elif len(segments) == 3 and segments[1] == "variant":
                                variant_rec = record["variants"][segments[2]]
                                owner.serve_path(self, inside(owner.project, variant_rec["path"]))
                            elif len(segments) == 3 and segments[1] == "texture":
                                tex_idx = texture_index(segments[2])
                                doc = json.loads(model_path.read_text(encoding="utf-8"))
                                texture = doc.get("textures", [])[tex_idx]
                                source = texture.get("source", "")
                                if source.startswith("data:image/"):
                                    self.response(*decode_data_uri(source))
                                else:
                                    owner.serve_path(self, owner.texture_path(model_path, texture))
                            else:
                                self.send_error(404)
                        elif owner.direct_model:
                            context = owner.asset(asset_id)
                            if segments[1:] == ["model"]:
                                self.response(json.dumps(owner.model_data(context.model, context.asset_id)).encode(), "application/json; charset=utf-8")
                            else:
                                self.send_error(404)
                        else:
                            self.send_error(404)
                    elif route == "/sandbox" or route.startswith("/sandbox/"):
                        owner.handle_sandbox(self, route, parsed.query)
                    elif route == "/api/file":
                        query = urllib.parse.parse_qs(parsed.query)
                        path = Path(query.get("path", [""])[0]).resolve()
                        owner.serve_path(self, path)
                    else:
                        self.send_error(404)
                except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                    pass
                except (json.JSONDecodeError, UnicodeDecodeError, binascii.Error) as exc:
                    # Corrupt data on disk is a server-side fault, not a confinement failure.
                    try:
                        self.response(json.dumps({"error": f"Corrupt data: {exc}"}).encode(), "application/json", 500)
                    except Exception:
                        pass
                except (PermissionError, ValueError) as exc:
                    try:
                        self.response(json.dumps({"error": str(exc)}).encode(), "application/json", 403)
                    except Exception:
                        pass
                except (FileNotFoundError, KeyError, IndexError) as exc:
                    try:
                        self.response(json.dumps({"error": str(exc)}).encode(), "application/json", 404)
                    except Exception:
                        pass
                except Exception as exc:
                    try:
                        self.response(json.dumps({"error": f"{type(exc).__name__}: {exc}"}).encode(), "application/json", 500)
                    except Exception:
                        pass

            def log_message(self, *_args):
                pass

        if self.projects_root is not None:
            # The default global port is a preference: a busy 8765 falls through the next ports. An explicit port is strict.
            if port == 0 or self._port_explicit:
                candidates = [port]
            else:
                candidates = range(port, port + GLOBAL_FALLBACK_PORTS + 1)
        else:
            candidates = [0] if port == 0 else range(port, port + 50)

        last = None
        for candidate in candidates:
            try:
                self.server = _ExclusiveServer((host, candidate), Handler)
                self.port = self.server.server_address[1]
                break
            except OSError as exc:
                last = exc
        else:
            raise ValueError(f"No viewer port available starting at {port}: {last}") from last

    def permitted(self, path):
        path = Path(path).resolve()
        if path in self.allowed_files:
            return path
        if self.projects_root is not None and path.is_relative_to(self.projects_root):
            return path
        if self.project is not None and path.is_relative_to(self.project):
            return path
        raise PermissionError("File is outside the allowed viewer root")

    def texture_path(self, model, record):
        reference = record.get("relative_path") or record.get("path")
        if not reference:
            raise FileNotFoundError("Texture has no embedded source or linked path")
        path = Path(reference)
        resolved = path if path.is_absolute() else model.parent / path
        return self.permitted(resolved)

    def model_data(self, path, asset_id=None, project_name=None):
        data = json.loads(path.read_text(encoding="utf-8"))
        for index, texture in enumerate(data.get("textures", [])):
            if texture.get("source", "").startswith("data:image/"):
                continue
            if project_name and asset_id:
                texture["relative_path"] = f"/api/p/{urllib.parse.quote(project_name)}/assets/{urllib.parse.quote(asset_id)}/texture/{index}"
            elif asset_id:
                texture["relative_path"] = f"/api/assets/{urllib.parse.quote(asset_id)}/texture/{index}"
            else:
                texture["relative_path"] = "/api/file?" + urllib.parse.urlencode({"path": str(self.texture_path(path, texture))})
            texture.pop("path", None)
        return data

    def serve_path(self, handler, path):
        path = self.permitted(path)
        if path.suffix.lower() == ".bbmodel":
            handler.response(json.dumps(self.model_data(path)).encode(), "application/json; charset=utf-8")
        else:
            handler.response(path.read_bytes(), mimetypes.guess_type(path.name)[0] or "application/octet-stream")

    def resolve_project_dir(self, project_name: str) -> Path:
        if not project_name or ".." in Path(project_name).parts or Path(project_name).is_absolute() or Path(project_name).drive:
            raise PermissionError("Invalid project identifier")

        if self.projects_root is None:
            if self.project is None:
                raise PermissionError("Viewer has no active project")
            allowed_ids = {self.project.name}
            if (self.project / "project.json").is_file():
                try:
                    allowed_ids.add(self.project_data(self.project).get("id"))
                except Exception:
                    pass
            if self.direct_model is not None:
                allowed_ids.add(self.direct_model.stem)

            if project_name not in allowed_ids:
                raise PermissionError(f"Access to project '{project_name}' is forbidden in scoped viewer")
            return self.project

        # Global mode
        cand = inside(self.projects_root, project_name)
        if cand.is_dir() and (cand / "project.json").is_file():
            return cand
        if self.projects_root.is_dir():
            for item in sorted(self.projects_root.iterdir()):
                if item.is_dir() and (item / "project.json").is_file():
                    try:
                        if self.project_data(item).get("id") == project_name:
                            return item
                    except Exception:
                        pass
        raise FileNotFoundError(f"Project '{project_name}' not found")

    def find_sandboxes(self, project_dir: Path) -> list[str]:
        sandboxes_dir = project_dir / "sandboxes"
        if not sandboxes_dir.is_dir():
            return []
        names = []
        for item in sorted(sandboxes_dir.iterdir()):
            if item.is_dir() and (item / "index.html").is_file():
                names.append(item.name)
        return names

    def find_glbs(self, project_dir: Path, data: dict) -> list[dict]:
        assets_dir = project_dir / "assets"
        if not assets_dir.is_dir():
            return []
        glbs = []
        registered_assets = data.get("assets", {})
        for glb_file in sorted(assets_dir.rglob("*.glb")):
            if not glb_file.is_file():
                continue
            rel = glb_file.relative_to(assets_dir)
            parts = rel.parts
            asset_id = parts[0] if len(parts) > 1 and parts[0] in registered_assets else None
            glbs.append({
                "path": rel.as_posix(),
                "stamp": stamp(glb_file),
                "asset": asset_id,
            })
        return glbs

    def list_projects(self) -> list[dict]:
        if self.projects_root is None:
            if self.project is not None:
                if (self.project / "project.json").is_file():
                    data = self.project_summary(self.project)
                    assets = []
                    for key, record in data.get("assets", {}).items():
                        m_rel = record.get("model", "")
                        m_path = inside(self.project, m_rel)
                        assets.append({
                            "id": key,
                            "name": record.get("name", key),
                            "has_model": m_path.is_file(),
                            "variant_count": len(record.get("variants", {})),
                        })
                    return [{
                        "id": data["id"],
                        "name": data.get("name", data["id"]),
                        "asset_count": len(assets),
                        "assets": assets,
                        "glbs": [],
                        "sandboxes": self.find_sandboxes(self.project),
                    }]
                elif self.direct_model is not None:
                    return [{
                        "id": self.direct_model.stem,
                        "name": self.direct_model.stem,
                        "asset_count": 1,
                        "assets": [{
                            "id": self.direct_model.stem,
                            "name": self.direct_model.stem,
                            "has_model": self.direct_model.is_file(),
                            "variant_count": 0,
                        }],
                        "glbs": [],
                        "sandboxes": [],
                    }]
            return []

        projects = []
        if self.projects_root.is_dir():
            for item in sorted(self.projects_root.iterdir()):
                if item.is_dir() and (item / "project.json").is_file():
                    try:
                        data = self.project_summary(item)
                        assets = []
                        for key, record in data.get("assets", {}).items():
                            m_rel = record.get("model", "")
                            m_path = inside(item, m_rel)
                            assets.append({
                                "id": key,
                                "name": record.get("name", key),
                                "has_model": m_path.is_file(),
                                "variant_count": len(record.get("variants", {})),
                            })
                        projects.append({
                            "id": data["id"],
                            "name": data.get("name", data["id"]),
                            "asset_count": len(assets),
                            "assets": assets,
                            "glbs": [],
                            "sandboxes": self.find_sandboxes(item),
                        })
                    except Exception:
                        pass
        return projects

    def asset(self, key, project_dir=None):
        target_project = project_dir or self.project
        if target_project is None:
            raise ValueError("Viewer has no active project")
        if (target_project / "project.json").exists():
            return resolve_asset(f"{target_project}#{key}")
        if self.direct_model is None or key != self.direct_model.stem:
            raise KeyError(key)
        from types import SimpleNamespace
        return SimpleNamespace(model=self.direct_model, project=self.direct_model.parent,
                               asset_id=self.direct_model.stem, record={"variants": {}},
                               texture_filter="nearest")

    def project_summary(self, project_dir):
        """The library needs identities, not a validation pass over every recipe and variant."""
        revision = stamp(project_dir / "project.json")
        with self._metadata_lock:
            cached = self._project_summaries.get(project_dir)
            if cached and cached[0] == revision:
                return cached[1]
            data = json.loads((project_dir / "project.json").read_text(encoding="utf-8-sig"))
            if data.get("schema") != 1 or not isinstance(data.get("assets"), dict):
                raise ValueError("Invalid project manifest")
            identifier(data.get("id"))
            for key in data["assets"]:
                identifier(key)
            self._project_summaries[project_dir] = (revision, data)
            return data

    def project_data(self, project_dir):
        """Validate a manifest once per revision; file-serving still checks confinement on every request."""
        revision = stamp(project_dir / "project.json")
        with self._metadata_lock:
            cached = self._project_metadata.get(project_dir)
            if cached and cached[0] == revision:
                return cached[1]
            data = load_project(project_dir)
            if len(self._project_metadata) >= 128:
                self._project_metadata.pop(next(iter(self._project_metadata)))
            self._project_metadata[project_dir] = (revision, data)
            return data

    def texture_metadata(self, model_path):
        """Cache only texture references, never embedded pixel data, until the model changes."""
        revision = stamp(model_path)
        with self._metadata_lock:
            cached = self._texture_metadata.get(model_path)
            if cached and cached[0] == revision:
                return cached[1]
            document = json.loads(model_path.read_text(encoding="utf-8"))
            textures = [{"embedded": texture.get("source", "").startswith("data:image/"),
                         "relative_path": texture.get("relative_path"), "path": texture.get("path")}
                        for texture in document.get("textures", [])]
            if len(self._texture_metadata) >= 512:
                self._texture_metadata.pop(next(iter(self._texture_metadata)))
            self._texture_metadata[model_path] = (revision, textures)
            return textures

    def catalog(self, project_dir=None, project_name=None, detail_asset=None):
        if project_dir is None:
            if self.project is None:
                raise ValueError("Viewer has no active project")
            project_dir = self.project
        if (project_dir / "project.json").exists():
            data = self.project_data(project_dir)
        elif self.direct_model is not None and (project_dir == self.direct_model.parent or project_dir == self.project):
            return self._direct_catalog()
        else:
            raise ValueError("Viewer has no registered project")

        if detail_asset == "":
            detail_asset = next(iter(data.get("assets", {})), None)
        assets = []
        p_prefix = f"/api/p/{urllib.parse.quote(project_name)}" if project_name else ""
        for key, record in data.get("assets", {}).items():
            model_path = inside(project_dir, record.get("model", ""))
            textures = []
            error = None
            if model_path.exists() and (detail_asset is None or detail_asset == key):
                try:
                    for index, texture in enumerate(self.texture_metadata(model_path)):
                        state = stamp(model_path) if texture["embedded"] else stamp(self.texture_path(model_path, texture))
                        tex_url = f"{p_prefix}/assets/{key}/texture/{index}" if p_prefix else f"/api/assets/{key}/texture/{index}"
                        textures.append({"url": tex_url, "stamp": state})
                except (ValueError, OSError, KeyError) as exc:
                    error = str(exc)
            var_prefix = f"{p_prefix}/assets/{key}/variant" if p_prefix else f"/api/assets/{key}/variant"
            variants = []
            for name, variant in record.get("variants", {}).items():
                v_path = inside(project_dir, variant["path"])
                variants.append({
                    "id": name,
                    "url": f"{var_prefix}/{name}",
                    "stamp": stamp(v_path) if v_path.exists() else None,
                })
            model_url = f"{p_prefix}/assets/{key}/model" if p_prefix else f"/api/assets/{key}/model"
            assets.append({
                "id": key,
                "name": record.get("name", key),
                "model_url": model_url,
                "stamp": stamp(model_path) if model_path.exists() else None,
                "textures": textures,
                "variants": variants,
                "default_variant": record.get("default_variant"),
                "texture_filter": record.get("texture_filter", "nearest"),
                "error": error,
            })
        return {
            "id": data["id"],
            "name": data.get("name", data["id"]),
            "assets": assets,
            "glbs": self.find_glbs(project_dir, data),
            "sandboxes": self.find_sandboxes(project_dir),
        }

    def _direct_catalog(self):
        """Single explicit file, no asset identity: no recipes, no variants."""
        model = self.direct_model
        key = model.stem
        textures, error = [], None
        if model.exists():
            try:
                document = json.loads(model.read_text(encoding="utf-8"))
                for index, texture in enumerate(document.get("textures", [])):
                    source = texture.get("source", "")
                    state = (stamp(model) if source.startswith("data:image/")
                             else stamp(self.texture_path(model, texture)))
                    textures.append({"url": f"/api/assets/{key}/texture/{index}", "stamp": state})
            except (ValueError, OSError, KeyError) as exc:
                error = str(exc)
        return {
            "id": key,
            "name": key,
            "assets": [{
                "id": key,
                "name": key,
                "model_url": f"/api/assets/{key}/model",
                "stamp": stamp(model),
                "textures": textures,
                "variants": [],
                "default_variant": None,
                "error": error,
            }],
            "glbs": [],
            "sandboxes": [],
        }

    def handle_project_api(self, handler, route: str, query_str: str):
        tail = route[len("/api/p/"):].lstrip("/")
        parts = tail.split("/")
        if not parts or not parts[0]:
            handler.send_error(404)
            return

        project_name = parts[0]
        project_dir = self.resolve_project_dir(project_name)

        if len(parts) == 2 and parts[1] == "glb":
            query = urllib.parse.parse_qs(query_str)
            path_arg = query.get("path", [""])[0]
            if not path_arg:
                raise ValueError("Missing path query parameter")
            assets_dir = project_dir / "assets"
            glb_path = inside(assets_dir, path_arg)
            if not glb_path.is_file() or glb_path.suffix.lower() != ".glb":
                raise FileNotFoundError(f"GLB not found: {path_arg}")
            handler.response(glb_path.read_bytes(), "model/gltf-binary")
        elif len(parts) >= 4 and parts[1] == "assets":
            asset_id = parts[2]
            p_data = self.project_data(project_dir)
            record = p_data.get("assets", {}).get(asset_id)
            if not record:
                raise KeyError(f"Asset '{asset_id}' not found in project '{project_name}'")
            model_path = inside(project_dir, record.get("model", ""))
            sub = parts[3:]
            if sub == ["model"]:
                data = self.model_data(model_path, asset_id, project_name=project_name)
                handler.response(json.dumps(data, ensure_ascii=False).encode(), "application/json; charset=utf-8")
            elif len(sub) == 2 and sub[0] == "variant":
                variant_name = sub[1]
                v_record = record.get("variants", {}).get(variant_name)
                if not v_record:
                    raise KeyError(f"Variant '{variant_name}' not found")
                self.serve_path(handler, inside(project_dir, v_record["path"]))
            elif len(sub) == 2 and sub[0] == "texture":
                tex_idx = texture_index(sub[1])
                data = json.loads(model_path.read_text(encoding="utf-8"))
                texture = data.get("textures", [])[tex_idx]
                source = texture.get("source", "")
                if source.startswith("data:image/"):
                    handler.response(*decode_data_uri(source))
                else:
                    self.serve_path(handler, self.texture_path(model_path, texture))
            else:
                handler.send_error(404)
        else:
            handler.send_error(404)

    def handle_sandbox(self, handler, route: str, raw_query: str = ""):
        parts = route[len("/sandbox/"):].split("/")
        if len(parts) < 2 or not parts[0] or not parts[1]:
            raise FileNotFoundError("Use /sandbox/<project>/<sandbox>/")
        project_dir = self.resolve_project_dir(parts[0])
        sandbox_name = parts[1]
        sandbox_dir = inside(project_dir / "sandboxes", sandbox_name)
        file_rel = "/".join(parts[2:]) or "index.html"
        target = inside(sandbox_dir, file_rel)
        if not sandbox_dir.is_dir():
            raise FileNotFoundError(f"Sandbox '{sandbox_name}' not found")
        if len(parts) == 2:
            if "\r" in route or "\n" in route:
                raise ValueError("Invalid sandbox route")
            location = urllib.parse.quote(route) + "/"
            if raw_query:
                location += "?" + raw_query
            handler.redirect(location)
            return
        if not target.is_file():
            raise FileNotFoundError(f"File '{file_rel}' not found in sandbox '{sandbox_name}'")
        mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if target.suffix.lower() == ".js":
            mime = "application/javascript; charset=utf-8"
        elif mime in ("text/html", "text/css"):
            mime += "; charset=utf-8"
        handler.response(target.read_bytes(), mime)

    def serve_lib(self, handler, route: str):
        rel = route[len("/lib/"):].lstrip("/")
        if not rel or ".." in Path(rel).parts or Path(rel).is_absolute() or Path(rel).drive:
            raise PermissionError("Path leaves allowed directory")
        target = None
        for candidate_dir in (VIEWER_DIR / "js", VIEWER_DIR / "vendor", VIEWER_DIR):
            try:
                cand = inside(candidate_dir, rel)
                if cand.is_file():
                    target = cand
                    break
            except ValueError:
                pass
        if target is None:
            handler.send_error(404)
            return
        ext = target.suffix.lower()
        if ext == ".js":
            mime = "application/javascript; charset=utf-8"
        elif ext == ".css":
            mime = "text/css; charset=utf-8"
        elif ext == ".html":
            mime = "text/html; charset=utf-8"
        elif ext == ".json":
            mime = "application/json; charset=utf-8"
        elif ext == ".glb":
            mime = "model/gltf-binary"
        else:
            mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        handler.response(target.read_bytes(), mime)

    def start(self):
        title = "Global viewer" if self.projects_root else "Project viewer"
        print(f"{title}: http://{self.host}:{self.port}/", flush=True)
        try:
            self.server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            self.server.server_close()
