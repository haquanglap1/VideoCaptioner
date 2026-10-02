"""The portable payload must retain every pinned OmniVoice recipe file."""

from scripts.package_test_models import copy_payload


def test_copy_keeps_model_attributes_but_excludes_secrets_and_caches(tmp_path):
    source = tmp_path / "source"
    tokenizer = source / "audio_tokenizer"
    tokenizer.mkdir(parents=True)
    (source / ".gitattributes").write_text("*.safetensors filter=lfs\n")
    (tokenizer / ".gitattributes").write_text("*.bin filter=lfs\n")
    (source / ".env").write_text("private-placeholder")
    (source / "install.log").write_text("private-placeholder")
    (source / "__pycache__").mkdir()
    (source / "__pycache__/private.pyc").write_bytes(b"cache")
    target = tmp_path / "payload"
    copy_payload(source, target)
    assert (target / ".gitattributes").read_bytes() == (source / ".gitattributes").read_bytes()
    assert (target / "audio_tokenizer/.gitattributes").read_bytes() == (tokenizer / ".gitattributes").read_bytes()
    assert not (target / ".env").exists()
    assert not (target / "install.log").exists()
    assert not (target / "__pycache__").exists()
