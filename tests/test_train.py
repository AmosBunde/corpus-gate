"""The training loop is provable on CPU; heavy pieces skip where the stack is absent."""

import json
from pathlib import Path

import pytest

from corpusgate.finetune import train


def test_config_pins_the_profiles() -> None:
    config = train.load_config()
    assert config["base_model"] == "Qwen/Qwen2.5-7B-Instruct"
    assert config["dry_run"]["max_steps"] == 2
    assert config["lora"]["r"] == 16


def test_pair_text_appends_completion_and_eos() -> None:
    pair = {"prompt": "P", "completion": '{"answer": "A"}'}
    text = train.pair_text(pair, "<eos>")
    assert text.startswith("P\n\nAssistant:") and text.endswith("<eos>")
    assert '{"answer": "A"}' in text


def test_cpu_guard_refuses_without_force(monkeypatch) -> None:
    torch = pytest.importorskip("torch")
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    with pytest.raises(SystemExit, match="needs a GPU"):
        train.resolve_device(force_cpu_ok=False)
    assert train.resolve_device(force_cpu_ok=True) == "cpu"


def test_dry_run_saved_adapter_is_loadable() -> None:
    pytest.importorskip("peft")
    adapter_dir = Path("registry/candidate/adapter")
    if not adapter_dir.exists():
        pytest.skip("dry-run adapter not present")
    from peft import PeftConfig

    config = PeftConfig.from_pretrained(adapter_dir)
    assert config.peft_type.value == "LORA"
    meta = json.loads((adapter_dir / "training_run.json").read_text())
    assert meta["dry_run"] is True and meta["steps"] == 2
