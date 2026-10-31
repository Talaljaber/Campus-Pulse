"""Import-graph guard for the layer rules of ARCHITECTURE 1.1.

Static (ast) checks only: no module is imported. P1.18 adds the runtime
``sys.modules`` assertions.
"""

from __future__ import annotations

import ast
import sys
from collections.abc import Callable
from pathlib import Path

PKG = "campuspulse_ai"
PKG_DIR = Path(__file__).resolve().parents[1] / PKG
STDLIB = set(sys.stdlib_module_names)


def _module_name(py_file: Path, root: Path, pkg: str) -> str:
    rel = py_file.relative_to(root).with_suffix("")
    parts = [pkg, *rel.parts]
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def imported_modules(py_file: Path, root: Path | None = None, pkg: str = PKG) -> set[str]:
    """Absolute dotted names imported by ``py_file`` (relative imports resolved).

    ``root`` is the package directory that maps to ``pkg``; it defaults to the
    real package directory.
    """
    root = root or PKG_DIR
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    here = _module_name(py_file, root, pkg).split(".")
    package_parts = here if py_file.name == "__init__.py" else here[:-1]
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package_parts[: len(package_parts) - (node.level - 1)]
                prefix = ".".join(base)
                mod = f"{prefix}.{node.module}" if node.module else prefix
            else:
                mod = node.module or ""
            found.add(mod)
            # `from pkg import sub` may import a submodule; record it too.
            found.update(f"{mod}.{a.name}" for a in node.names if a.name != "*")
    return found


def _under(name: str, prefix: str) -> bool:
    return name == prefix or name.startswith(prefix + ".")


def violations(
    layer_dir: Path,
    allowed: Callable[[str], bool],
    root: Path | None = None,
    pkg: str = PKG,
) -> list[tuple[Path, str]]:
    """Every (file, imported module) in ``layer_dir`` that ``allowed`` rejects."""
    bad = []
    for py_file in sorted(layer_dir.rglob("*.py")):
        for mod in sorted(imported_modules(py_file, root, pkg)):
            top = mod.split(".")[0]
            # Names synthesised from `from X import name` are only checked via X.
            if mod.startswith(pkg + ".") and not allowed(mod) and _is_synthetic(mod):
                continue
            if not allowed(mod) and top != "":
                bad.append((py_file, mod))
    return bad


def _is_synthetic(mod: str) -> bool:
    """True when ``mod`` is an imported *name* (class/function), not a module."""
    parts = mod.split(".")
    return parts[-1][:1].isupper() or parts[-1].isupper()


def _stdlib(name: str) -> bool:
    return name.split(".")[0] in STDLIB


def test_domain_stdlib_only() -> None:
    def ok(m: str) -> bool:
        return _stdlib(m) or _under(m, f"{PKG}.domain")

    assert violations(PKG_DIR / "domain", ok) == []


# LD-36: application/dto.py is the HTTP contract and may use pydantic (a validation library,
# not a web framework). Every other application module stays domain + numpy only.
DTO_MODULE = PKG_DIR / "application" / "dto.py"


def test_application_domain_numpy_only() -> None:
    def ok(m: str) -> bool:
        return (
            _stdlib(m)
            or _under(m, f"{PKG}.domain")
            or _under(m, f"{PKG}.application")
            or _under(m, "numpy")
        )

    found = violations(PKG_DIR / "application", ok)
    assert [(f, m) for f, m in found if not (f == DTO_MODULE and _under(m, "pydantic"))] == []


def test_adapters_do_not_import_frameworks_or_composition() -> None:
    forbidden = (
        f"{PKG}.frameworks",
        f"{PKG}.composition",
        "fastapi",
        "starlette",
        "uvicorn",
        "flask",
        "django",
    )

    def ok(m: str) -> bool:
        return not any(_under(m, f) for f in forbidden)

    assert violations(PKG_DIR / "adapters", ok) == []
    # Nothing outside frameworks/ imports frameworks (entry points live outside the package).
    for layer in ("domain", "application", "adapters", "composition", "config"):
        d = PKG_DIR / layer
        bad = violations(d, lambda m: not _under(m, f"{PKG}.frameworks")) if d.exists() else []
        assert bad == [], f"{layer} imports frameworks: {bad}"


def test_frameworks_import_only_composition_and_dto() -> None:
    allowed_prefixes = (
        f"{PKG}.frameworks",
        f"{PKG}.composition",
        f"{PKG}.application.dto",
        f"{PKG}.config",
        f"{PKG}.domain",
        "fastapi",
        "starlette",
        "uvicorn",
        "argparse",
        "pydantic",
        "pydantic_settings",
        "psutil",
    )

    def ok(m: str) -> bool:
        # The bare package import is only for ``__version__``.
        return _stdlib(m) or m in (PKG, f"{PKG}.__version__") or any(_under(m, p) for p in allowed_prefixes)

    assert violations(PKG_DIR / "frameworks", ok) == []


def test_checker_flags_forbidden_import(tmp_path: Path) -> None:
    root = tmp_path / "fakepkg"
    domain = root / "domain"
    domain.mkdir(parents=True)
    (domain / "__init__.py").write_text("")
    (domain / "bad.py").write_text("import requests\nfrom . import values\nimport os\n")

    def ok(m: str) -> bool:
        return _stdlib(m) or _under(m, "fakepkg.domain")

    found = violations(domain, ok, root=root, pkg="fakepkg")
    assert [(p.name, m) for p, m in found] == [("bad.py", "requests")]
