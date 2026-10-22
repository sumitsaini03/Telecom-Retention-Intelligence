"""Build and verify the distributable project ZIP without caches or secrets."""

from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "telecom-retention-intelligence-final.zip"
EXCLUDED_DIRS = {".git", ".venv", ".pytest_cache", "__pycache__", ".task-deps", "dist", "build"}


def include(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    if any(part in EXCLUDED_DIRS for part in relative.parts):
        return False
    if path == ARCHIVE or path.suffix == ".pyc" or path.name == ".env":
        return False
    if path.name.startswith(".env.") and path.name != ".env.example":
        return False
    if path.suffix == ".log" or path.name.endswith("_exit_code.txt") or path.name == "test-results.xml":
        return False
    if path.name.endswith(".download.csv"):
        return False
    return path.is_file()


def main() -> None:
    files = sorted((path for path in ROOT.rglob("*") if include(path)), key=lambda path: path.as_posix().lower())
    if not files:
        raise RuntimeError("No project files were selected for packaging")
    with ZipFile(ARCHIVE, "w", compression=ZIP_DEFLATED, compresslevel=8) as bundle:
        for path in files:
            bundle.write(path, path.relative_to(ROOT).as_posix())
    with ZipFile(ARCHIVE, "r") as bundle:
        corrupt_member = bundle.testzip()
        names = bundle.namelist()
        if corrupt_member:
            raise RuntimeError(f"ZIP CRC validation failed for {corrupt_member}")
        required = {
            "README.md", "src/analysis.py", "sql/analysis.sql", "outputs/metrics.json",
            "outputs/postgres_validation.json", "tests/test_analysis.py", "powerbi/BUILD_GUIDE.md",
            "RESUME_PROJECT_ENTRY.md",
        }
        missing = sorted(required - set(names))
        if missing:
            raise RuntimeError(f"ZIP is missing required files: {missing}")
    print(f"Archive: {ARCHIVE}")
    print(f"Files: {len(files)}")
    print(f"Bytes: {ARCHIVE.stat().st_size}")
    print("CRC: passed")


if __name__ == "__main__":
    main()
