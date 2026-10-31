"""Generate docs/api/endpoints.md from services/ai/openapi.json and services/ai/tests/fixtures/api/*.json.

Usage (from the repo root):
    python scripts/gen_api_docs.py           # (re)write docs/api/endpoints.md
    python scripts/gen_api_docs.py --check   # exit 1 if the file is missing or stale (CI)

Stdlib only; the output is deterministic (no timestamps), UTF-8, LF line endings.
For every operation it writes: method and path, purpose, roles and auth, parameters, the request
schema, a full `curl.exe` example (PowerShell syntax), the full example response, the other fixtures,
the error codes with the error shape, and side effects. A schema reference follows.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
OPENAPI = ROOT / "services" / "ai" / "openapi.json"
FIXTURES = ROOT / "services" / "ai" / "tests" / "fixtures" / "api"
OUT = ROOT / "docs" / "api" / "endpoints.md"
REF_PREFIX = "#/components/schemas/"


def load_json(path: Path) -> Any:
    """Read JSON, tolerating a UTF-8 BOM (PowerShell 5.1 redirects add one)."""
    return json.loads(path.read_text(encoding="utf-8-sig"))


def anchor(name: str) -> str:
    """GitHub-style anchor for a schema heading."""
    return "schema-" + name.lower()


def escape(text: str) -> str:
    """Make text safe inside a Markdown table cell."""
    return text.replace("|", "\\|").replace("\n", " ")


def type_of(schema: dict[str, Any]) -> str:
    """A compact, human-readable type for one JSON schema node."""
    if "$ref" in schema:
        name = schema["$ref"].removeprefix(REF_PREFIX)
        return f"[{name}](#{anchor(name)})"
    if "anyOf" in schema:
        return " \\| ".join(type_of(s) for s in schema["anyOf"])
    if "const" in schema:
        return f"`{json.dumps(schema['const'], ensure_ascii=False)}`"
    if "enum" in schema:
        return " \\| ".join(f"`{v}`" for v in schema["enum"])
    kind = schema.get("type")
    if kind == "array":
        if "prefixItems" in schema:
            return "[" + ", ".join(type_of(s) for s in schema["prefixItems"]) + "]"
        return f"array of {type_of(schema.get('items', {}))}"
    if kind == "object":
        extra = schema.get("additionalProperties")
        if isinstance(extra, dict):
            return f"object of {type_of(extra)}"
        return "object"
    if kind == "string" and schema.get("format"):
        return f"string ({schema['format']})"
    if kind is None:
        return "any"
    return str(kind)


def constraints(schema: dict[str, Any]) -> str:
    """Bounds and defaults worth showing next to a field."""
    parts = []
    for key, label in (
        ("minimum", ">="),
        ("exclusiveMinimum", ">"),
        ("maximum", "<="),
        ("minLength", "min len"),
    ):
        if key in schema:
            parts.append(f"{label} {schema[key]}")
    for sub in schema.get("anyOf", []):
        if sub.get("type") != "null":
            parts.extend(c for c in [constraints(sub)] if c)
    return ", ".join(parts)


def field_table(schema: dict[str, Any]) -> list[str]:
    """Markdown table of an object schema's properties."""
    props = schema.get("properties", {})
    if not props:
        return ["_(no fields)_"]
    required = set(schema.get("required", []))
    lines = ["| Field | Type | Required | Notes |", "| --- | --- | --- | --- |"]
    for name, prop in props.items():
        notes = [prop.get("description", "").strip().rstrip(".")]
        if "default" in prop:
            notes.append(f"default `{json.dumps(prop['default'], ensure_ascii=False)}`")
        bounds = constraints(prop)
        if bounds:
            notes.append(bounds)
        note = escape("; ".join(n for n in notes if n))
        lines.append(f"| `{name}` | {type_of(prop)} | {'yes' if name in required else 'no'} | {note} |")
    return lines


def json_block(value: Any) -> list[str]:
    """A fenced JSON block."""
    return ["```json", json.dumps(value, ensure_ascii=False, indent=2), "```"]


def curl_example(op: dict[str, Any], method: str, fixture: dict[str, Any]) -> list[str]:
    """A full curl.exe command (PowerShell) reproducing `fixture`, plus any body file it reads."""
    url = fixture["path"]
    for key, value in fixture["path_params"].items():
        url = url.replace("{" + key + "}", value)
    if fixture["query"]:
        url += "?" + "&".join(f"{k}={quote(str(v), safe='')}" for k, v in fixture["query"].items())
    auth = op.get("x-auth")
    lines: list[str] = []
    files: list[str] = []
    args = [f'curl.exe -s -X {method.upper()} "$env:AI_URL{url}"']
    if auth == "service_token":
        args.append('-H "Authorization: Bearer $env:AI_SERVICE_TOKEN"')
        args.append('-H "X-CP-User-JWT: $env:USER_JWT"')
    for key, value in fixture["headers"].items():
        if not key.lower().startswith("x-cp-"):
            args.append(f'-H "{key}: {value}"')
    request = fixture["request"]
    if op.get("requestBody", {}).get("content", {}).get("multipart/form-data"):
        upload = request["files"]["file"]
        files += [f"`{upload['filename']}`:", "", "```csv", upload["content"].rstrip("\n"), "```", ""]
        args.append(f'-F "file=@{upload["filename"]};type=text/csv"')
        args += [f'-F "{k}={v}"' for k, v in request["form"].items()]
    elif request is not None:
        files += ["`request.json`:", "", *json_block(request), ""]
        args.append('-H "Content-Type: application/json"')
        args.append('--data-binary "@request.json"')
    lines += files
    lines += ["```powershell", " `\n  ".join(args), "```"]
    return lines


def error_shape_lines() -> list[str]:
    """The standard error body, shown once at the top."""
    return json_block({"error": {"code": "<error code>", "message": "<human-readable>", "details": None}})


def render(openapi: dict[str, Any], fixtures: list[dict[str, Any]]) -> str:
    """The whole endpoints.md text."""
    schemas = openapi.get("components", {}).get("schemas", {})
    out = [
        "# API endpoints",
        "",
        "> **Generated** by `python scripts/gen_api_docs.py` from `services/ai/openapi.json` and "
        "`services/ai/tests/fixtures/api/*.json`. Do not edit by hand; CI runs `--check`.",
        "> Auth, status values, flags, error codes and versioning: [README.md](README.md).",
        "",
        f"API version `{openapi['info']['version']}`, OpenAPI `{openapi['openapi']}`. "
        "Examples use PowerShell with `curl.exe`; set `$env:AI_URL` (no trailing slash), "
        "`$env:AI_SERVICE_TOKEN` and, for user calls, `$env:USER_JWT` (the user's Supabase access token). "
        'Request bodies are read from a file (`--data-binary "@request.json"`) because PowerShell 5.1 '
        "mangles inline JSON quotes.",
        "",
        "Every non-2xx response has this shape:",
        "",
        *error_shape_lines(),
        "",
        "## Contents",
        "",
    ]
    ops = [(path, method, op) for path, item in openapi["paths"].items() for method, op in item.items()]
    for path, method, op in ops:
        out.append(f"- [`{method.upper()} {path}`](#{op['operationId']}) {op.get('summary', '')}")
    out += ["- [Schemas](#schemas)", ""]

    for path, method, op in ops:
        mine = [
            f
            for f in fixtures
            if f["method"].lower() == method and path in (f["path"], *f.get("alias_paths", []))
        ]
        ok = [f for f in mine if f["status_code"] < 400]
        primary = next((f for f in ok if f.get("default")), ok[0] if ok else None)
        out += [f'<a id="{op["operationId"]}"></a>', f"## `{method.upper()} {path}`", ""]
        out += [f"**{op.get('summary', '')}.** {op.get('description', '')}", ""]
        roles = ", ".join(f"`{r}`" for r in op.get("x-roles", []))
        auth = {
            "service_token": "service token",
            "hmac": "HMAC signature (`Linear-Signature`)",
            "none": "none",
        }
        out += [
            f"- **Roles:** {roles}",
            f"- **Auth:** {auth.get(op.get('x-auth', ''), op.get('x-auth'))}",
            "",
        ]

        params = [p for p in op.get("parameters", []) if not p["name"].startswith("x-cp-")]
        if params:
            out += [
                "**Parameters**",
                "",
                "| Name | In | Type | Required | Notes |",
                "| --- | --- | --- | --- | --- |",
            ]
            for p in params:
                note = escape(p.get("description") or "")
                out.append(
                    f"| `{p['name']}` | {p['in']} | {type_of(p['schema'])} | "
                    f"{'yes' if p.get('required') else 'no'} | {note} |"
                )
            out.append("")
        if any(p["name"].startswith("x-cp-") for p in op.get("parameters", [])):
            out += ["Identity headers: `X-CP-User-JWT` (see [README › Auth](README.md#auth)).", ""]

        body = op.get("requestBody")
        out += ["**Request body**", ""]
        if body is None:
            out += ["None.", ""]
        else:
            for media, content in body.get("content", {}).items():
                schema = content.get("schema", {})
                out.append(
                    f"`{media}`: {type_of(schema)}"
                    + (f". {body['description']}" if "description" in body else "")
                )
                ref = schema.get("$ref", "").removeprefix(REF_PREFIX)
                if ref in schemas:
                    out += ["", *field_table(schemas[ref])]
            out.append("")

        success = [(c, r) for c, r in op["responses"].items() if c.startswith("2")]
        for code, response in success:
            media = ", ".join(
                f"`{m}` {type_of(c.get('schema', {}))}" for m, c in response.get("content", {}).items()
            )
            out += [f"**Response `{code}`:** {media}", ""]

        if primary is not None:
            out += [f"**Example** (fixture `{primary['name']}`): {primary['description']}", ""]
            out += curl_example(op, method, primary)
            out += ["", f"Response `{primary['status_code']}`:", ""]
            if isinstance(primary["response"], str):
                out += ["```csv", primary["response"].rstrip("\n"), "```"]
            else:
                out += json_block(primary["response"])
            out.append("")
        others = [f for f in mine if f is not primary]
        if others:
            out += ["**More examples** (send `X-Mock-Fixture: <name>` to the mock app to get one)", ""]
            out += ["| Fixture | Status | What it shows |", "| --- | --- | --- |"]
            for f in others:
                out.append(f"| `{f['name']}` | {f['status_code']} | {escape(f['description'])} |")
            out.append("")
        errors = [f for f in mine if f["status_code"] >= 400]
        for f in errors[:1]:
            out += [f"Error example (`{f['name']}`, {f['status_code']}):", "", *json_block(f["response"]), ""]

        out += ["**Errors**", "", "| HTTP | Codes |", "| --- | --- |"]
        for code, response in op["responses"].items():
            if not code.startswith("2"):
                out.append(f"| {code} | {escape(response.get('description', ''))} |")
        out += ["", "**Side effects**", ""]
        out += [f"- {s}" for s in op.get("x-side-effects", [])] or ["- none"]
        out.append("")

    out += ['<a id="schemas"></a>', "## Schemas", ""]
    for name in sorted(schemas):
        schema = schemas[name]
        out += [f'<a id="{anchor(name)}"></a>', f"### {name}", ""]
        if schema.get("description"):
            out += [schema["description"].strip().replace("\n", " "), ""]
        if "enum" in schema:
            out += ["Values: " + ", ".join(f"`{v}`" for v in schema["enum"]), ""]
        else:
            out += [*field_table(schema), ""]
    return "\n".join(out).rstrip("\n") + "\n"


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; see the module docstring."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--check", action="store_true", help="exit 1 if docs/api/endpoints.md is stale")
    args = parser.parse_args(argv)
    fixtures = [load_json(p) for p in sorted(FIXTURES.glob("*.json"))]
    text = render(load_json(OPENAPI), fixtures)
    if args.check:
        current = OUT.read_bytes().decode("utf-8") if OUT.exists() else None
        if current != text:
            print(f"{OUT.relative_to(ROOT).as_posix()} is stale: run `python scripts/gen_api_docs.py`")
            return 1
        print(f"{OUT.relative_to(ROOT).as_posix()} is up to date")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(text.encode("utf-8"))
    print(f"wrote {OUT.relative_to(ROOT).as_posix()} ({len(openapi_ops(load_json(OPENAPI)))} operations)")
    return 0


def openapi_ops(openapi: dict[str, Any]) -> list[tuple[str, str]]:
    """(method, path) for every operation."""
    return [(m, p) for p, item in openapi["paths"].items() for m in item]


if __name__ == "__main__":
    raise SystemExit(main())
