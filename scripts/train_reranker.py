#!/usr/bin/env python3
"""Fine-tune the MiniLM cross-encoder reranker on the synthetic training set.

Loads the train/val JSONL produced by generate_reranker_training_set.py and fine-tunes
cross-encoder/ms-marco-MiniLM-L-6-v2 via a single sentence_transformers CrossEncoder.fit() call
across all epochs, using binary (1.0/0.0) relevance labels. A custom evaluator computes
validation loss - via BCEWithLogitsLoss over the model's raw prediction logits, since fit()'s
built-in evaluators report accuracy-style scores rather than loss - once per epoch, and saves
whichever epoch's checkpoint had the lowest validation loss (see _ValidationLossEvaluator for
why it saves the checkpoint itself rather than via fit()'s own save_best_model). Training runs
as one fit(epochs=N, ...) call rather than N separate fit(epochs=1) calls so the LR schedule and
optimizer momentum carry across epochs instead of resetting every epoch.

Requires the `training` extra (`pip install -e ".[training]"`) for CrossEncoder.fit()'s
`datasets`/`accelerate` dependencies, on top of the base sentence-transformers dependency.

Usage example:
python scripts/train_reranker.py \
    --train data/reranker/train.jsonl \
    --val data/reranker/val.jsonl \
    --output-dir models/reranker/finetuned \
    --epochs 3
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.retrieval.reranker import DEFAULT_FINETUNED_MODEL_PATH, PRETRAINED_MODEL_NAME


def load_examples(path: str) -> List[Tuple[str, str, float]]:
    """Load (query, doc_text, label) triples from a JSONL file of {query, doc_text, label}."""
    data_path = Path(path)
    if not data_path.exists():
        raise FileNotFoundError(f"Training data not found: {path}")

    examples: List[Tuple[str, str, float]] = []
    with data_path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_no} of {path}: {exc}") from exc
            examples.append((record["query"], record["doc_text"], float(record["label"])))

    return examples


def _compute_val_loss(model: Any, val_pairs: List[Tuple[str, str]], val_labels: Any) -> float:
    """Binary cross-entropy over raw (pre-activation) prediction logits, matching the loss
    CrossEncoder.fit() trains against for a num_labels=1 model with binary float labels."""
    import torch

    logits = model.predict(
        val_pairs,
        activation_fn=torch.nn.Identity(),
        convert_to_tensor=True,
        show_progress_bar=False,
    )
    logits = logits.view(-1).to("cpu")
    return torch.nn.functional.binary_cross_entropy_with_logits(logits, val_labels).item()


class _ValidationLossEvaluator:
    """Evaluator hook that sentence_transformers' CrossEncoder.fit() calls once per epoch
    (via EvaluatorCallback.on_epoch_end). Computes validation BCE loss and saves the model
    itself whenever it's the best seen so far, rather than delegating to fit()'s own
    save_best_model machinery: that path relies on EvaluatorCallback.trainer being wired up
    after the CrossEncoderTrainer is constructed, which fit() never does for a plain (non-dict)
    evaluator callable, so SaveModelCallback.on_evaluate never fires and no checkpoint is ever
    written - confirmed by an end-to-end run where evaluator.history was populated but no model
    files appeared under output_dir. Saving directly from here, where the live model instance is
    already in hand, sidesteps that broken wiring entirely."""

    def __init__(self, val_pairs: List[Tuple[str, str]], val_labels: Any, output_dir: Path):
        self._val_pairs = val_pairs
        self._val_labels = val_labels
        self._output_dir = output_dir
        self.history: List[Tuple[int, float]] = []
        self.best_val_loss = float("inf")
        self.best_epoch = -1

    def __call__(
        self, model: Any, output_path: Optional[str] = None, epoch: int = -1, steps: int = -1
    ) -> Dict[str, float]:
        # `epoch` arrives as a float (e.g. 1.0) from the trainer's epoch-progress tracking;
        # rounded to an int here since it's only ever used for whole-epoch reporting.
        epoch_num = int(round(epoch))
        print(
            f"[epoch {epoch_num}] evaluating on {len(self._val_pairs)} validation examples...",
            end=" ",
            flush=True,
        )
        val_loss = _compute_val_loss(model, self._val_pairs, self._val_labels)
        self.history.append((epoch_num, val_loss))

        is_best = val_loss < self.best_val_loss
        if is_best:
            self.best_val_loss = val_loss
            self.best_epoch = epoch_num
            model.save(str(self._output_dir))
        print(f"val_loss={val_loss:.4f}{' (new best, checkpoint saved)' if is_best else ''}")

        return {"val_loss": val_loss}


def train_reranker(
    train_path: str = "data/reranker/train.jsonl",
    val_path: str = "data/reranker/val.jsonl",
    output_dir: str = DEFAULT_FINETUNED_MODEL_PATH,
    base_model: str = PRETRAINED_MODEL_NAME,
    epochs: int = 3,
    batch_size: int = 16,
    learning_rate: float = 2e-5,
    warmup_ratio: float = 0.1,
    seed: int = 42,
) -> Dict[str, Any]:
    """Fine-tune `base_model` on `train_path`, evaluating on `val_path` after every epoch, and
    save the lowest-validation-loss checkpoint to `output_dir`."""
    if not 1 <= epochs:
        raise ValueError(f"epochs must be a positive integer, got {epochs}.")

    train_examples = load_examples(train_path)
    if not train_examples:
        raise ValueError(f"No training examples found in {train_path}.")
    print(f"Loaded {len(train_examples)} training examples from {train_path}")

    val_examples = load_examples(val_path)
    if not val_examples:
        raise ValueError(f"No validation examples found in {val_path}.")
    print(f"Loaded {len(val_examples)} validation examples from {val_path}")

    import torch
    from sentence_transformers import CrossEncoder, InputExample
    from torch.utils.data import DataLoader

    torch.manual_seed(seed)

    print(f"Loading base model '{base_model}' (downloads from HuggingFace on first use)...")
    model = CrossEncoder(base_model, num_labels=1)
    print(f"Model loaded on device: {model.model.device}")

    train_dataloader = DataLoader(
        [InputExample(texts=[query, doc], label=label) for query, doc, label in train_examples],
        shuffle=True,
        batch_size=batch_size,
    )
    val_pairs = [(query, doc) for query, doc, _ in val_examples]
    val_labels = torch.tensor([label for _, _, label in val_examples], dtype=torch.float32)

    total_steps = len(train_dataloader) * epochs
    warmup_steps = max(1, int(total_steps * warmup_ratio))

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    evaluator = _ValidationLossEvaluator(val_pairs, val_labels, output_path)

    print(
        f"Training for {epochs} epoch(s), batch_size={batch_size}, "
        f"~{len(train_dataloader)} steps/epoch ({total_steps} steps total), "
        f"warmup_steps={warmup_steps}"
    )
    # A single fit() call trains one coherent multi-epoch schedule (LR warmup/decay and
    # optimizer momentum carry across epochs); calling fit(epochs=1) in a loop instead would
    # reset both every epoch. The evaluator saves the best checkpoint itself - see
    # _ValidationLossEvaluator's docstring for why fit()'s own save_best_model doesn't work here.
    # show_progress_bar=True surfaces the trainer's live step/loss/ETA bar - without it the
    # process looks hung for however long one epoch takes, with no output at all in between.
    model.fit(
        train_dataloader,
        evaluator=evaluator,
        epochs=epochs,
        warmup_steps=warmup_steps,
        optimizer_params={"lr": learning_rate},
        show_progress_bar=True,
    )

    if not evaluator.history:
        raise RuntimeError("Training completed without recording any validation evaluation.")
    print(f"Training complete after {len(evaluator.history)} epoch(s).")

    if evaluator.best_epoch == -1 or not any(output_path.iterdir()):
        raise RuntimeError(
            f"No checkpoint was saved to {output_path} - validation loss may have been "
            "non-finite on every epoch."
        )

    return {
        "epochs_trained": epochs,
        "best_epoch": evaluator.best_epoch,
        "best_val_loss": evaluator.best_val_loss,
        "output_dir": str(output_path),
        "num_train_examples": len(train_examples),
        "num_val_examples": len(val_examples),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fine-tune the MiniLM cross-encoder reranker on the synthetic training set, "
            "saving the lowest-validation-loss checkpoint."
        )
    )
    parser.add_argument(
        "--train", default="data/reranker/train.jsonl", help="Path to the training JSONL."
    )
    parser.add_argument(
        "--val", default="data/reranker/val.jsonl", help="Path to the validation JSONL."
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_FINETUNED_MODEL_PATH,
        help="Directory to save the fine-tuned checkpoint to.",
    )
    parser.add_argument(
        "--base-model",
        default=PRETRAINED_MODEL_NAME,
        help="Pretrained cross-encoder checkpoint to fine-tune from.",
    )
    parser.add_argument(
        "--epochs", type=int, default=3, help="Number of training epochs (2-4 recommended)."
    )
    parser.add_argument("--batch-size", type=int, default=16, help="Training batch size.")
    parser.add_argument("--learning-rate", type=float, default=2e-5, help="AdamW learning rate.")
    parser.add_argument(
        "--warmup-ratio",
        type=float,
        default=0.1,
        help="Fraction of total training steps used for LR warmup.",
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="Random seed for training data shuffling."
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        result = train_reranker(
            train_path=args.train,
            val_path=args.val,
            output_dir=args.output_dir,
            base_model=args.base_model,
            epochs=args.epochs,
            batch_size=args.batch_size,
            learning_rate=args.learning_rate,
            warmup_ratio=args.warmup_ratio,
            seed=args.seed,
        )
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}")
        return 1

    print(
        f"Best checkpoint from epoch {result['best_epoch']}/{result['epochs_trained']} "
        f"(val_loss={result['best_val_loss']:.4f}) saved to {result['output_dir']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
