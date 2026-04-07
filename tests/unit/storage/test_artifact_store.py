"""Tests for ArtifactStore: store, retrieve, list_artifacts, delete, checksum."""

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

        rel_path = await store.store(run_id, ArtifactType.PLAN, data)

        full_path = tmp_path / rel_path
        assert full_path.exists()
        assert full_path.read_bytes() == data

    async def test_store_creates_file_with_string(self, store: ArtifactStore, tmp_path: Path):
        run_id = uuid4()
        data = '{"verdict": "approve"}'

        rel_path = await store.store(run_id, ArtifactType.REVIEW, data)

        full_path = tmp_path / rel_path
        assert full_path.read_bytes() == data.encode("utf-8")

    async def test_store_returns_relative_path(self, store: ArtifactStore):
        run_id = uuid4()

        rel_path = await store.store(run_id, ArtifactType.PLAN, b"{}")

        assert rel_path.startswith("runs/")
        assert str(run_id) in rel_path

    async def test_store_default_filename_json(self, store: ArtifactStore):
        run_id = uuid4()

        rel_path = await store.store(run_id, ArtifactType.PLAN, b"{}")

        assert rel_path.endswith("plan.json")

    async def test_store_diff_uses_patch_extension(self, store: ArtifactStore):
        run_id = uuid4()

        rel_path = await store.store(run_id, ArtifactType.DIFF, b"diff --git ...")

        assert rel_path.endswith("diff.patch")

    async def test_store_custom_filename(self, store: ArtifactStore, tmp_path: Path):
        run_id = uuid4()
        data = b"custom content"

        rel_path = await store.store(
            run_id, ArtifactType.PLAN, data, filename="my_plan_v2.json"
        )

        assert rel_path.endswith("my_plan_v2.json")
        full_path = tmp_path / rel_path
        assert full_path.read_bytes() == data

    async def test_store_creates_parent_directories(self, store: ArtifactStore, tmp_path: Path):
        run_id = uuid4()

        await store.store(run_id, ArtifactType.PLAN, b"{}")

        run_dir = tmp_path / "runs" / str(run_id)
        assert run_dir.is_dir()

    async def test_store_multiple_artifacts_same_run(self, store: ArtifactStore):
        run_id = uuid4()

        path1 = await store.store(run_id, ArtifactType.PLAN, b'{"plan": true}')
        path2 = await store.store(run_id, ArtifactType.REVIEW, b'{"review": true}')

        assert path1 != path2


# -- retrieve ------------------------------------------------------------------


class TestRetrieve:
    async def test_retrieve_returns_stored_bytes(self, store: ArtifactStore):
        run_id = uuid4()
        data = b'{"key": "value"}'

        rel_path = await store.store(run_id, ArtifactType.PLAN, data)
        result = await store.retrieve(rel_path)

        assert result == data

    async def test_retrieve_nonexistent_raises_file_not_found(self, store: ArtifactStore):
        with pytest.raises(FileNotFoundError, match="Artifact not found"):
            await store.retrieve("runs/nonexistent/plan.json")

    async def test_retrieve_roundtrip_string_data(self, store: ArtifactStore):
        run_id = uuid4()
        original = '{"steps": [1, 2, 3]}'

        rel_path = await store.store(run_id, ArtifactType.PLAN, original)
        result = await store.retrieve(rel_path)

        assert result.decode("utf-8") == original


# -- list_artifacts ------------------------------------------------------------


class TestListArtifacts:
    async def test_list_artifacts_returns_all_files(self, store: ArtifactStore):
        run_id = uuid4()

        await store.store(run_id, ArtifactType.PLAN, b"{}")
        await store.store(run_id, ArtifactType.REVIEW, b"{}")
        await store.store(run_id, ArtifactType.DIFF, b"diff")

        paths = await store.list_artifacts(run_id)

        assert len(paths) == 3

    async def test_list_artifacts_returns_relative_paths(self, store: ArtifactStore):
        run_id = uuid4()
        await store.store(run_id, ArtifactType.PLAN, b"{}")

        paths = await store.list_artifacts(run_id)

        assert len(paths) == 1
        assert paths[0].startswith("runs/")
        assert str(run_id) in paths[0]

    async def test_list_artifacts_empty_run_returns_empty(self, store: ArtifactStore):
        run_id = uuid4()

        paths = await store.list_artifacts(run_id)

        assert paths == []

    async def test_list_artifacts_does_not_cross_runs(self, store: ArtifactStore):
        run_a = uuid4()
        run_b = uuid4()

        await store.store(run_a, ArtifactType.PLAN, b"{}")
        await store.store(run_b, ArtifactType.REVIEW, b"{}")

        paths_a = await store.list_artifacts(run_a)
        paths_b = await store.list_artifacts(run_b)

        assert len(paths_a) == 1
        assert len(paths_b) == 1
        assert str(run_a) in paths_a[0]
        assert str(run_b) in paths_b[0]


# -- delete --------------------------------------------------------------------


class TestDelete:
    async def test_delete_removes_file(self, store: ArtifactStore, tmp_path: Path):
        run_id = uuid4()
        rel_path = await store.store(run_id, ArtifactType.PLAN, b"{}")

        await store.delete(rel_path)

        assert not (tmp_path / rel_path).exists()

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
