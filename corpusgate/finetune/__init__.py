"""Pair curation, decontamination, LoRA training, and the adapter registry.

Filled in milestone M4. Training pairs are deduplicated against the
eval set by embedding similarity before any training run.
"""
