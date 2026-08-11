"""Reusable grounded RAG components.

Heavy retrieval/model modules are intentionally not imported at package import
time so the compact desktop sidecar can run without CUDA/transformers.
"""
