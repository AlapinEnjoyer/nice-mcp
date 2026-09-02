"""Safe creation and installation of immutable corpus archives."""

import shutil
import tarfile
import tempfile
from pathlib import Path

from nice_mcp.corpus.snapshot import file_checksum, load_snapshot


def package_snapshot(snapshot: Path, output: Path) -> Path:
    """Create a compressed snapshot artifact plus checksum sidecar."""
    snapshot = snapshot.resolve(strict=True)
    manifest, _ = load_snapshot(snapshot)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    with tarfile.open(temporary, "w:gz") as archive:
        archive.add(snapshot, arcname=f"nicegui-corpus-{manifest.corpus_revision.removeprefix('sha256:')}")
    checksum = file_checksum(temporary)
    temporary.replace(output)
    output.with_suffix(output.suffix + ".sha256").write_text(f"{checksum}  {output.name}\n", encoding="utf-8")
    return output


def inspect_artifact(archive_path: Path) -> list[str]:
    """Validate archive members and return their names without extraction."""
    with tarfile.open(archive_path, "r:gz") as archive:
        names = []
        for member in archive.getmembers():
            path = Path(member.name)
            if path.is_absolute() or ".." in path.parts or member.issym() or member.islnk():
                raise ValueError(f"unsafe corpus artifact member: {member.name}")
            names.append(member.name)
        return names


def install_artifact(archive_path: Path, destination: Path) -> Path:
    """Safely extract and validate an immutable artifact."""
    names = inspect_artifact(archive_path)
    if not names:
        raise ValueError("empty corpus artifact")
    destination.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".install-", dir=destination))
    try:
        with tarfile.open(archive_path, "r:gz") as archive:
            archive.extractall(staging, filter="data")
        roots = [item for item in staging.iterdir() if item.is_dir()]
        if len(roots) != 1:
            raise ValueError("corpus artifact must contain one snapshot root")
        manifest, _ = load_snapshot(roots[0])
        target = destination / manifest.corpus_revision.removeprefix("sha256:")
        if target.exists():
            return target
        roots[0].replace(target)
        return target
    finally:
        shutil.rmtree(staging, ignore_errors=True)
