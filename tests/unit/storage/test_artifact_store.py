"""Tests for ArtifactStore: store, retrieve, list_artifacts, delete, checksum."""

import hashlib
from pathlib import Path
from uuid import uuid4

import pytest

from foundry.storage.artifact_store import ArtifactStore, ArtifactType


@pytest.fixture
def store(tmp_path: Path) -> ArtifactStore:
    """Return an ArtifactStore rooted in a temporary directory."""
    return ArtifactStore(base_path=str(tmp_path))


# -- store ---------------------------------------------------------------------


class TestStore:
    async def test_store_creates_file_with_bytes(self, store: ArtifactStore, tmp_path: Path):
        run_id = uuid4()
        data = b'{"steps": []}'

        result = await store.store(run_id, ArtifactType.PLAN, data)

        full_path = tmp_path / result["storage_path"]
        assert full_path.exists()
        assert full_path.read_bytes() == data

    async def test_store_creates_file_with_string(self, store: ArtifactStore, tmp_path: Path):
        run_id = uuid4()
        data = '{"verdict": "approve"}'

        result = await store.store(run_id, ArtifactType.REVIEW, data)

        full_path = tmp_path / result["storage_path"]
        assert full_path.read_bytes() == data.encode("utf-8")

    async def test_store_returns_dict_with_storage_path(self, store: ArtifactStore):
        run_id = uuid4()

        result = await store.store(run_id, ArtifactType.PLAN, b"{}")

        assert "storage_path" in result
        assert result["storage_path"].startswith("runs/")
        assert str(run_id) in result["storage_path"]

    async def test_store_returns_size_bytes(self, store: ArtifactStore):
        run_id = uuid4()
        data = b'{"key": "value"}'

        result = await store.store(run_id, ArtifactType.PLAN, data)

        assert result["size_bytes"] == len(data)

    async def test_store_returns_sha256_checksum(self, store: ArtifactStore):
        run_id = uuid4()
        data = b'{"key": "value"}'

        result = await store.store(run_id, ArtifactType.PLAN, data)

        expected = hashlib.sha256(data).hexdigest()
        assert result["checksum"] == expected
        assert len(result["checksum"]) == 64

    async def test_store_string_size_matches_encoded(self, store: ArtifactStore):
        run_id = uuid4()
        data = "hello world"

        result = await store.store(run_id, ArtifactType.PLAN, data)

        assert result["size_bytes"] == len(data.encode("utf-8"))

    async def test_store_string_checksum_matches_encoded(self, store: ArtifactStore):
        run_id = uuid4()
        data = "hello world"

        result = await store.store(run_id, ArtifactType.PLAN, data)

        expected = hashlib.sha256(data.encode("utf-8")).hexdigest()
        assert result["checksum"] == expected

    async def test_store_default_filename_json(self, store: ArtifactStore):
        run_id = uuid4()

        result = await store.store(run_id, ArtifactType.PLAN, b"{}")

        assert result["storage_path"].endswith("plan.json")

    async def test_store_diff_uses_patch_extension(self, store: ArtifactStore):
        run_id = uuid4()

        result = await store.store(run_id, ArtifactType.DIFF, b"diff --git ...")

        assert result["storage_path"].endswith("diff.patch")

    async def test_store_custom_filename(self, store: ArtifactStore, tmp_path: Path):
        run_id = uuid4()
        data = b"custom content"

        result = await store.store(
            run_id, ArtifactType.PLAN, data, filename="my_plan_v2.json"
        )

        assert result["storage_path"].endswith("my_plan_v2.json")
        full_path = tmp_path / result["storage_path"]
        assert full_path.read_bytes() == data

    async def test_store_creates_parent_directories(self, store: ArtifactStore, tmp_path: Path):
        run_id = uuid4()

        await store.store(run_id, ArtifactType.PLAN, b"{}")

        run_dir = tmp_path / "runs" / str(run_id)
        assert run_dir.is_dir()

    async def test_store_multiple_artifacts_same_run(self, store: ArtifactStore):
        run_id = uuid4()

        r1 = await store.store(run_id, ArtifactType.PLAN, b'{"plan": true}')
        r2 = await store.store(run_id, ArtifactType.REVIEW, b'{"review": true}')

        assert r1["storage_path"] != r2["storage_path"]

    async def test_store_overwrites_existing_artifact(self, store: ArtifactStore, tmp_path: Path):
        run_id = uuid4()

        await store.store(run_id, ArtifactType.PLAN, b"v1")
        r2 = await store.store(run_id, ArtifactType.PLAN, b"v2")

        full_path = tmp_path / r2["storage_path"]
        assert full_path.read_bytes() == b"v2"
        assert r2["size_bytes"] == 2


# -- retrieve ------------------------------------------------------------------


class TestRetrieve:
    async def test_retrieve_returns_stored_bytes(self, store: ArtifactStore):
        run_id = uuid4()
        data = b'{"key": "value"}'

        result = await store.store(run_id, ArtifactType.PLAN, data)
        retrieved = await store.retrieve(result["storage_path"])

        assert retrieved == data

    async def test_retrieve_nonexistent_raises_file_not_found(self, store: ArtifactStore):
        with pytest.raises(FileNotFoundError, match="Artifact not found"):
            await store.retrieve("runs/nonexistent/plan.json")

    async def test_retrieve_roundtrip_string_data(self, store: ArtifactStore):
        run_id = uuid4()
        original = '{"steps": [1, 2, 3]}'

        result = await store.store(run_id, ArtifactType.PLAN, original)
        retrieved = await store.retrieve(result["storage_path"])

        assert retrieved.decode("utf-8") == original


# -- list_artifacts ------------------------------------------------------------


class TestListArtifacts:
    async def test_list_artifacts_returns_all_files(self, store: ArtifactStore):
        run_id = uuid4()

        await store.store(run_id, ArtifactType.PLAN, b"{}")
        await store.store(run_id, ArtifactType.REVIEW, b"{}")
        await store.store(run_id, ArtifactType.DIFF, b"diff")

        entries = await store.list_artifacts(run_id)

        assert len(entries) == 3

    async def test_list_artifacts_returns_dicts_with_required_keys(self, store: ArtifactStore):
        run_id = uuid4()
        await store.store(run_id, ArtifactType.PLAN, b'{"plan": true}')

        entries = await store.list_artifacts(run_id)

        assert len(entries) == 1
        entry = entries[0]
        assert "filename" in entry
        assert "size_bytes" in entry
        assert "modified" in entry

    async def test_list_artifacts_filename_matches(self, store: ArtifactStore):
        run_id = uuid4()
        await store.store(run_id, ArtifactType.PLAN, b"{}")

        entries = await store.list_artifacts(run_id)

        assert entries[0]["filename"] == "plan.json"

    async def test_list_artifacts_size_matches(self, store: ArtifactStore):
        run_id = uuid4()
        data = b'{"steps": [1, 2, 3]}'
        await store.store(run_id, ArtifactType.PLAN, data)

        entries = await store.list_artifacts(run_id)

        assert entries[0]["size_bytes"] == len(data)

    async def test_list_artifacts_modified_is_iso_timestamp(self, store: ArtifactStore):
        run_id = uuid4()
        await store.store(run_id, ArtifactType.PLAN, b"{}")

        entries = await store.list_artifacts(run_id)

        # ISO format should contain 'T' separator and timezone info
        assert "T" in entries[0]["modified"]

    async def test_list_artifacts_empty_run_returns_empty(self, store: ArtifactStore):
        run_id = uuid4()

        entries = await store.list_artifacts(run_id)

        assert entries == []

    async def test_list_artifacts_does_not_cross_runs(self, store: ArtifactStore):
        run_a = uuid4()
        run_b = uuid4()

        await store.store(run_a, ArtifactType.PLAN, b"{}")
        await store.store(run_b, ArtifactType.REVIEW, b"{}")

        entries_a = await store.list_artifacts(run_a)
        entries_b = await store.list_artifacts(run_b)

        assert len(entries_a) == 1
        assert len(entries_b) == 1
        assert entries_a[0]["filename"] == "plan.json"
        assert entries_b[0]["filename"] == "review.json"


# -- delete --------------------------------------------------------------------


class TestDelete:
    async def test_delete_removes_file(self, store: ArtifactStore, tmp_path: Path):
        run_id = uuid4()
        result = await store.store(run_id, ArtifactType.PLAN, b"{}")

        await store.delete(result["storage_path"])

        assert not (tmp_path / result["storage_path"]).exists()

    async def test_delete_nonexistent_is_noop(self, store: ArtifactStore):
        # Should not raise
        await store.delete("runs/nonexistent/plan.json")


# -- get_checksum --------------------------------------------------------------


class TestChecksum:
    def test_checksum_bytes(self, store: ArtifactStore):
        data = b"hello world"
        checksum = store.get_checksum(data)

        assert isinstance(checksum, str)
        assert len(checksum) == 64  # SHA-256 hex digest

    def test_checksum_string(self, store: ArtifactStore):
        checksum = store.get_checksum("hello world")

        assert isinstance(checksum, str)
        assert len(checksum) == 64

    def test_checksum_deterministic(self, store: ArtifactStore):
        data = b"same data"

        assert store.get_checksum(data) == store.get_checksum(data)

    def test_checksum_bytes_and_string_match(self, store: ArtifactStore):
        text = "hello world"

        assert store.get_checksum(text) == store.get_checksum(text.encode("utf-8"))

    async def test_store_checksum_matches_get_checksum(self, store: ArtifactStore):
        """The checksum returned by store() matches get_checksum() for the same data."""
        run_id = uuid4()
        data = b"consistency check"

        result = await store.store(run_id, ArtifactType.PLAN, data)

        assert result["checksum"] == store.get_checksum(data)
