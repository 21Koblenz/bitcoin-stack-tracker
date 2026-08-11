from pathlib import Path


def test_bulk_import_schema_accepts_import_ref_hash():
    root = Path(__file__).resolve().parents[1]
    text = (root / "custom_components/bitcoin_stack_tracker/__init__.py").read_text(encoding="utf-8")
    block = text.split("IMPORT_TRANSACTION_SCHEMA = vol.Schema({", 1)[1].split("BULK_IMPORT_SCHEMA = vol.Schema({", 1)[0]
    assert 'vol.Optional("import_ref_hash", default=""): cv.string' in block


def test_normal_transaction_schema_does_not_need_import_ref_hash():
    root = Path(__file__).resolve().parents[1]
    text = (root / "custom_components/bitcoin_stack_tracker/__init__.py").read_text(encoding="utf-8")
    block = text.split("TRANSACTION_SCHEMA = vol.Schema({", 1)[1].split("ADD_STACK_SCHEMA = vol.Schema({", 1)[0]
    assert 'import_ref_hash' not in block
