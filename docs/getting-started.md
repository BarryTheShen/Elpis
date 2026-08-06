# Getting started

For a full **local install** (uv, `config.yaml`, `.env`, first run), see
[installation.md](installation.md). To run digests automatically, set
`CONDENSEIT_SCHEDULER_ENABLED=1` in `.env` — no cron or launchd needed. See
[scheduling.md](scheduling.md) for details and optional external scheduling.

Quick path:

1. Copy `config.example.yaml` to `config.yaml` and adjust feeds and channels.
2. Choose an LLM backend in **Admin > Providers**:
   - **Ollama (local)**: install Ollama and pull a model (`ollama pull llama3.2:3b`).
   - **Hosted providers**: choose OpenRouter, OpenAI, Anthropic, Gemini, Groq,
     Mistral, DeepSeek, or Together AI, then save its API key.
   - **Custom OpenAI-compatible**: enter the server base URL, normally ending in
     `/v1`, and save a key if the server requires one.
3. Set the model, reasoning effort, and optional thinking budget in **Admin > LLM**.
4. Install deps: `uv sync` (see [installation.md](installation.md)) or a
   venv with `pip install -e ".[dev]"`.
5. Run the complete Elpis app: `elpis serve` (or `make docker-up` for Docker).
6. Run a digest: use **Run digest** in the header, or `uv run elpis run`
   (or `elpis run` if your shell uses the project venv).

The web UI gives you the digest reader, rating controls, read-later actions,
and admin pages in one place. This screenshot uses generated demo data.

To open Elpis like a native app on your phone, see
[add-to-home-screen.md](add-to-home-screen.md).

![Desktop digest reader with demo data](assets/demo/desktop-digest.png)

See [configuration.md](configuration.md) for YAML and environment variables.

For **Docker UI + host digest**, dry runs, and what each script does, see
[scripts.md](scripts.md).

Optional: `bash scripts/install.sh` (or `bash install.sh` from the repo root)
prints cron and LaunchAgent snippets from your chosen time and cadence (see
[installation.md](installation.md)).
