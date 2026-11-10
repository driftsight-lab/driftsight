import pytest

from src.convert.check_lettucedetect_onnx import onnx_size_mib
from src.convert.resolve_revision import is_pinned, write_revision

SHA = "0123456789abcdef0123456789abcdef01234567"


def test_is_pinned_rejects_branch_names():
    assert is_pinned(SHA)
    for bad in ("", None, "main", SHA[:7], SHA.upper()):
        assert not is_pinned(bad)


def test_write_revision_keeps_comments(tmp_path):
    path = tmp_path / "m.yaml"
    path.write_text('# 주석\nrepo: a/b\n# 해시\nrevision: ""\nmax_length: 8\n', encoding="utf-8")
    write_revision(path, SHA)
    assert path.read_text(encoding="utf-8") == (
        f"# 주석\nrepo: a/b\n# 해시\nrevision: {SHA}\nmax_length: 8\n"
    )
    with pytest.raises(ValueError):  # 이미 고정된 값은 다시 쓰지 않는다
        write_revision(path, SHA)


def test_onnx_size_counts_external_data(tmp_path):
    (tmp_path / "model.onnx").write_bytes(b"0" * 2**20)
    (tmp_path / "model.onnx_data").write_bytes(b"0" * 2**20)
    (tmp_path / "config.json").write_text("{}")
    assert onnx_size_mib(tmp_path) == 2.0
    (tmp_path / "empty").mkdir()
    with pytest.raises(FileNotFoundError):
        onnx_size_mib(tmp_path / "empty")
