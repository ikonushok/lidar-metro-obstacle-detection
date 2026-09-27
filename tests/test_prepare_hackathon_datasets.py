import tarfile
import tempfile
import unittest
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "prepare_hackathon_datasets",
    ROOT / "scripts" / "prepare_hackathon_datasets.py",
)
prepare_hackathon_datasets = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(prepare_hackathon_datasets)

extract_bag = prepare_hackathon_datasets.extract_bag
materialize_archive = prepare_hackathon_datasets.materialize_archive


def write_tar(path: Path, files: dict[str, bytes]) -> None:
    with tarfile.open(path, "w") as archive:
        for name, payload in files.items():
            source = tempfile.NamedTemporaryFile(delete=False)
            try:
                source.write(payload)
                source.close()
                archive.add(source.name, arcname=name)
            finally:
                Path(source.name).unlink(missing_ok=True)


class PrepareHackathonDatasetsTests(unittest.TestCase):
    def test_materialize_archives_and_extract_selected_bag(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "dataset" / "raw"
            catalog = root / "dataset" / "for_hackathon"
            extracted = root / "dataset" / "extracted"
            raw.mkdir(parents=True)
            write_tar(
                raw / "for_hackathon.tar",
                {
                    "for_hackathon/doubleT_obstacle/metadata.yaml": b"metadata",
                    "for_hackathon/doubleT_obstacle/doubleT_obstacle_0.db3": b"sqlite",
                },
            )

            target = materialize_archive(raw, catalog, "for_hackathon", copy=True)
            self.assertEqual(target, catalog / "for_hackathon")
            self.assertTrue(target.is_file())

            extract_bag(catalog, extracted, "doubleT_obstacle")
            self.assertEqual((extracted / "doubleT_obstacle" / "metadata.yaml").read_bytes(), b"metadata")
            self.assertEqual((extracted / "doubleT_obstacle" / "doubleT_obstacle_0.db3").read_bytes(), b"sqlite")

    def test_existing_valid_catalog_archive_is_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "dataset" / "raw"
            catalog = root / "dataset" / "for_hackathon"
            raw.mkdir(parents=True)
            catalog.mkdir(parents=True)
            write_tar(catalog / "new_data", {"new_data/metadata.yaml": b"metadata"})

            target = materialize_archive(raw, catalog, "new_data", copy=False)
            self.assertEqual(target, catalog / "new_data")


if __name__ == "__main__":
    unittest.main()
