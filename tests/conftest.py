from __future__ import annotations

from pathlib import Path

import pytest

from tests.fixtures.build import build_all

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def generated_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    dest = tmp_path_factory.mktemp("cv_files")
    return build_all(dest)


@pytest.fixture(scope="session")
def digital_pdf(generated_dir: Path) -> Path:
    return generated_dir / "digital.pdf"


@pytest.fixture(scope="session")
def two_column_pdf(generated_dir: Path) -> Path:
    return generated_dir / "two_column.pdf"


@pytest.fixture(scope="session")
def multipage_pdf(generated_dir: Path) -> Path:
    return generated_dir / "multipage.pdf"


@pytest.fixture(scope="session")
def low_text_pdf(generated_dir: Path) -> Path:
    return generated_dir / "low_text.pdf"


@pytest.fixture(scope="session")
def sample_docx(generated_dir: Path) -> Path:
    return generated_dir / "sample.docx"
