"""Offline guards for the reproducible CI bootstrap."""

from pathlib import Path
import stat
import sys
import zipfile
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mtg_play.ci_prepare import extract, fetch, prepare
from mtg_play.connection_proof import ProofError


def test_existing_destination_is_never_modified(tmp_path):
    sentinel = tmp_path / "original"
    sentinel.write_text("unchanged")
    with pytest.raises(ProofError, match="CI_DESTINATION_ALREADY_EXISTS"):
        prepare(tmp_path, tmp_path)
    assert sentinel.read_text() == "unchanged"


def test_corrupt_cached_archive_is_rejected_without_network(tmp_path):
    (tmp_path / "engine.zip").write_bytes(b"corrupt")
    with pytest.raises(ProofError, match="CI_ARCHIVE_HASH_MISMATCH"):
        fetch(dict(url="unused", sha256="0" * 64), tmp_path, "engine")


@pytest.mark.parametrize(
    "name", ["root/../../escape", "root/C:/escape", "root/..\\escape"]
)
def test_archive_cannot_escape_destination(tmp_path, name):
    archive = tmp_path / "input.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(name, "bad")
    with pytest.raises(ProofError, match="UNSAFE_CI_ARCHIVE_PATH"):
        extract(archive, dict(prefix="root/", destination=""), tmp_path / "out")
    assert not (tmp_path / "escape").exists()


def test_archive_links_are_rejected(tmp_path):
    archive = tmp_path / "input.zip"
    member = zipfile.ZipInfo("root/link")
    member.create_system = 3
    member.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(member, "../../escape")
    with pytest.raises(ProofError, match="UNSUPPORTED_CI_ARCHIVE_LINK"):
        extract(archive, dict(prefix="root/", destination=""), tmp_path / "out")
