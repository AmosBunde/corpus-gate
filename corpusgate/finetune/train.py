"""LoRA training over the decontaminated pairs: one code path, two profiles.

The full profile targets the pinned base model and expects a GPU; it
refuses to start on CPU unless explicitly forced, because a 7B
full-corpus run on CPU is a mistake, not a choice. The dry-run
profile drives the identical load, tokenize, train, save path with a
tiny stand-in model and two optimizer steps, which is the pre-rental
proof that the loop works and the shape CI-adjacent validation uses.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import yaml

CONFIG_PATH = "configs/finetune.yaml"


def load_config(path: str | Path = CONFIG_PATH) -> dict:
    return yaml.safe_load(Path(path).read_text())


def load_pairs(pairs_path: str | Path) -> list[dict]:
    return [json.loads(x) for x in Path(pairs_path).read_text().splitlines()]


def pair_text(pair: dict, eos_token: str) -> str:
    """One training sequence per pair: prompt, then the exact schema completion."""
    return f"{pair['prompt']}\n\nAssistant: {pair['completion']}{eos_token}"


def resolve_device(force_cpu_ok: bool) -> str:
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if force_cpu_ok:
        return "cpu"
    raise SystemExit(
        "make finetune needs a GPU for the full profile; rent the 24 GB session, "
        "or run the dry run with --dry-run, or force with FINETUNE_ALLOW_CPU=1."
    )


def train(
    pairs_path: str | Path,
    out_dir: str | Path,
    dry_run: bool = False,
    config_path: str | Path = CONFIG_PATH,
) -> Path:
    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer

    config = load_config(config_path)
    profile = config["dry_run"] if dry_run else config["training"]
    model_name = config["dry_run"]["base_model"] if dry_run else config["base_model"]
    device = "cpu" if dry_run else resolve_device(os.environ.get("FINETUNE_ALLOW_CPU") == "1")

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(model_name)
    lora = config["lora"]
    target_modules = lora["target_modules"] if not dry_run else "all-linear"
    model = get_peft_model(
        model,
        LoraConfig(
            r=lora["r"],
            lora_alpha=lora["alpha"],
            lora_dropout=lora["dropout"],
            target_modules=target_modules,
            task_type="CAUSAL_LM",
        ),
    )
    model.to(device)
    model.train()

    pairs = load_pairs(pairs_path)
    texts = [pair_text(p, tokenizer.eos_token or "") for p in pairs]
    max_len = profile["max_seq_len"]
    batch_size = profile["batch_size"]
    optimizer = torch.optim.AdamW(
        (p for p in model.parameters() if p.requires_grad),
        lr=config["training"]["learning_rate"],
    )
    max_steps = profile.get("max_steps")
    epochs = 1 if dry_run else config["training"]["epochs"]

    step = 0
    last_loss = None
    for _epoch in range(epochs):
        for start in range(0, len(texts), batch_size):
            batch = tokenizer(
                texts[start : start + batch_size],
                truncation=True,
                max_length=max_len,
                padding=True,
                return_tensors="pt",
            ).to(device)
            labels = batch["input_ids"].clone()
            labels[batch["attention_mask"] == 0] = -100
            loss = model(**batch, labels=labels).loss
            loss.backward()
            optimizer.step()
            optimizer.zero_grad()
            step += 1
            last_loss = float(loss)
            if step % 10 == 0 or (max_steps and step >= max_steps):
                print(f"step {step} loss {last_loss:.4f}")
            if max_steps and step >= max_steps:
                break
        if max_steps and step >= max_steps:
            break

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(out_dir)
    (out_dir / "training_run.json").write_text(
        json.dumps(
            {
                "base_model": model_name,
                "dry_run": dry_run,
                "steps": step,
                "final_loss": last_loss,
                "pairs": len(pairs),
                "device": device,
            },
            indent=2,
        )
        + "\n"
    )
    return out_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs", default="registry/candidate/pairs.jsonl")
    parser.add_argument("--out", default="registry/candidate/adapter")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    out = train(args.pairs, args.out, dry_run=args.dry_run)
    meta = json.loads((out / "training_run.json").read_text())
    print(f"adapter saved to {out} ({meta['steps']} steps, loss {meta['final_loss']:.4f}, "
          f"{meta['device']}, dry_run={meta['dry_run']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
