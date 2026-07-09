import argparse

import src.main as main_module


def _args(persist_directory, clean):
    return argparse.Namespace(
        pdf_directory="data/papers",
        md_directory=None,
        persist_directory=persist_directory,
        clean=clean,
    )


def test_clean_removes_existing_vectorstore_before_ingesting(tmp_path, monkeypatch):
    persist_dir = tmp_path / "chroma_db"
    persist_dir.mkdir()
    (persist_dir / "stale.bin").write_text("old data")

    calls = []
    monkeypatch.setattr(main_module, "validate_runtime_config", lambda: (True, "OK"))
    monkeypatch.setattr(
        "populate_vectorstore.populate_vectorstore",
        lambda **kwargs: calls.append(kwargs) or object(),
    )

    result = main_module.run_ingest(_args(str(persist_dir), clean=True))

    assert result == 0
    assert not persist_dir.exists()  # wiped before populate_vectorstore ran
    assert calls == [
        {
            "pdf_directory": "data/papers",
            "md_directory": None,
            "persist_directory": str(persist_dir),
        }
    ]


def test_without_clean_existing_vectorstore_is_preserved(tmp_path, monkeypatch):
    persist_dir = tmp_path / "chroma_db"
    persist_dir.mkdir()
    (persist_dir / "existing.bin").write_text("keep me")

    monkeypatch.setattr(main_module, "validate_runtime_config", lambda: (True, "OK"))
    monkeypatch.setattr("populate_vectorstore.populate_vectorstore", lambda **kwargs: object())

    result = main_module.run_ingest(_args(str(persist_dir), clean=False))

    assert result == 0
    assert (persist_dir / "existing.bin").exists()


def test_run_ingest_fails_fast_on_invalid_config(monkeypatch):
    monkeypatch.setattr(
        main_module, "validate_runtime_config", lambda: (False, "OPENAI_API_KEY not set")
    )

    result = main_module.run_ingest(_args("./chroma_db", clean=False))

    assert result == 1
