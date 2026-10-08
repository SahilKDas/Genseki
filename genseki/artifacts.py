"""Read-only artifact provenance and integrity diagnostics; no substitutions."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re


def sha256_file(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _resolve(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or '\\' in relative:
        raise ValueError('artifact path must be relative POSIX notation')
    path = Path(relative)
    if path.is_absolute() or PureWindowsPath(relative).drive or '..' in path.parts:
        raise ValueError('artifact path escapes root')
    target = (root / path).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError('artifact path escapes root')
    return target


def _private(value) -> bool:
    if isinstance(value, str):
        return bool(re.search(
            r'(?i)[a-z]:[\\/]|[\\/]users[\\/]|/home/|traceback|(?:^|[\s=\"\x27])[\\/]\S+',
            value))
    if isinstance(value, dict):
        return any(_private(k) or _private(v) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return any(_private(v) for v in value)
    return False


def portable_value(root: Path | str, value):
    """Remove host-specific paths from report metadata, preserving local notation."""
    root = Path(root).resolve()
    if isinstance(value, Path):
        path = value.resolve()
        return path.relative_to(root).as_posix() if path.is_relative_to(root) else '<external-artifact>'
    if isinstance(value, str):
        for spelling in (str(root), root.as_posix()):
            value = value.replace(spelling+'\\', '').replace(spelling+'/', '')
        return '<redacted-host-metadata>' if _private(value) else value
    if isinstance(value, dict):
        return {portable_value(root, k): portable_value(root, v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [portable_value(root, v) for v in value]
    return value


def create_manifest(root: Path | str, artifacts: dict[str, str | None], *,
                    provenance: dict, effective_settings: dict) -> dict:
    root = Path(root)
    manifest = dict(schema_version=1, provenance=provenance,
                    effective_settings=effective_settings, artifacts={})
    for role, path in artifacts.items():
        manifest['artifacts'][role] = None if path is None else dict(
            path=path, sha256=sha256_file(_resolve(root, path)))
    issues = verify_manifest(root, manifest)
    if issues:
        raise ValueError('; '.join(issues))
    return manifest


def verify_manifest(root: Path | str, manifest: dict, *, check_sources: bool = True) -> list[str]:
    """Return sanitized issues, never mutate artifacts or report host paths."""
    issues = []
    if not isinstance(manifest, dict) or manifest.get('schema_version') != 1:
        return ['unsupported manifest schema']
    if _private(manifest):
        issues.append('identifying path or traceback in manifest')
    provenance = manifest.get('provenance', {})
    if not isinstance(provenance, dict):
        return issues + ['invalid provenance']
    kind = provenance.get('kind')
    if kind not in ('verified-source-build', 'imported-binary'):
        issues.append('invalid build provenance kind')
    sources = provenance.get('source_files', {})
    if kind == 'verified-source-build':
        for field in ('revision', 'compiler', 'dependencies', 'build_command', 'source_files'):
            if not provenance.get(field):
                issues.append('missing build provenance: ' + field)
        if provenance.get('build_exit_code') != 0:
            issues.append('source build has no successful exit evidence')
    settings = manifest.get('effective_settings', {})
    if not isinstance(settings, dict):
        issues.append('invalid effective settings')
    else:
        requested, verified = settings.get('requested'), settings.get('verified')
        if not isinstance(requested, dict) or not isinstance(verified, dict):
            issues.append('missing requested/verified settings')
        elif requested != verified:
            issues.append('requested settings differ from verified settings')
        if not settings.get('evidence'):
            issues.append('missing effective-settings evidence')
    artifacts = manifest.get('artifacts')
    if not isinstance(artifacts, dict) or not artifacts:
        return issues + ['missing artifact identities']
    if not artifacts.get('executable'):
        issues.append('missing executable identity')
    entries = list(artifacts.values())
    if isinstance(sources, dict):
        if check_sources:
            entries += [dict(path=p, sha256=h) for p, h in sources.items()]
        elif any(not isinstance(p, str) or not isinstance(h, str)
                 or not re.fullmatch('[0-9a-f]{64}', h) for p, h in sources.items()):
            issues.append('invalid source identities')
        if not check_sources:
            for p in sources:
                try:
                    _resolve(Path(root), p)
                except (ValueError, TypeError, OSError):
                    issues.append('unsafe source identity path')
    else:
        issues.append('invalid source identities')
    for index, entry in enumerate(entries):
        if entry is None:
            continue
        label = f'artifact {index}'
        if not isinstance(entry, dict):
            issues.append(label + ': invalid record')
            continue
        expected = entry.get('sha256')
        if not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected):
            issues.append(label + ': invalid SHA256')
            continue
        try:
            path = _resolve(Path(root), entry.get('path'))
            actual = sha256_file(path)
        except (ValueError, TypeError, OSError):
            issues.append(label + ': missing, unreadable or unsafe path')
            continue
        if actual != expected:
            issues.append(label + ': SHA256 mismatch')
    return issues


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    try:
        with args.manifest.open(encoding='utf-8') as stream:
            manifest = json.load(stream)
        issues = verify_manifest(args.root, manifest)
    except (OSError, ValueError, TypeError):
        issues = ['manifest unreadable or malformed']
    print(json.dumps(dict(schema_version=1, valid=not issues, issues=issues)))
    return int(bool(issues))


if __name__ == '__main__':
    raise SystemExit(main())
