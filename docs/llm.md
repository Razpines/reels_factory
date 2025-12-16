# LLM setup

The pipeline uses a local Llama-compatible model for rewrite/hook/hashtags and optional gender detection. To keep setup lightweight, use a small, quantized model.

## Recommended model
- **Model:** `TheBloke/Llama-2-7B-Chat-GGUF` (or similar 7B chat model)
- **File:** `llama-2-7b-chat.Q4_K_M.gguf` (fits on most GPUs, OK on CPU)
- **Source:** https://huggingface.co/TheBloke/Llama-2-7B-Chat-GGUF

Place the downloaded `.gguf` in `models/` and point to it in config if you change the filename/path.

## Why small + quantized?
- Faster tokens/sec on consumer GPUs/CPUs
- Lower VRAM/RAM footprint
- Good enough for rewrite + simple classification tasks

## How to download (CLI)
```bash
mkdir -p models
hf_hub_download --repo-id TheBloke/Llama-2-7B-Chat-GGUF \
  --filename llama-2-7b-chat.Q4_K_M.gguf \
  --local-dir models
```
Or download directly from the Hugging Face page.

## Config tips
- Default path in code: `models/llama-3.1-8b-instruct-q6_k.gguf` (change if you swap models).
- If you’re CPU-only, prefer Q4 or Q5 quantization and smaller context (`n_ctx`).
- Keep the model out of git; `.gitignore` already excludes `models/`.
