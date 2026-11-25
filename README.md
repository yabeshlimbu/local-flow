# LocalFlow

Voice dictation for macOS that runs entirely on your Mac. Hold a key in any app, speak, let go, and polished text appears at your cursor. Speech recognition uses Whisper (MLX on Apple Silicon) and editing uses a local LLM through Ollama. Nothing leaves the machine and there's no word limit.

## Start it

```bash
open LocalFlow.app
```

`LocalFlow.app` launches the code in this folder, so keep the folder where it is. You can drag the app to `/Applications` or add it to *Login Items* so it starts at login. If you move the folder, rebuild the app with `packaging/build_app.sh`. You can also run it from a terminal with `./run.sh`.

### One-time macOS setup
1. **Accessibility** and **Input Monitoring**: System Settings → Privacy & Security → add and enable **LocalFlow**. The hotkey starts by itself once these are granted, so you don't need to restart.
2. **Microphone**: macOS asks the first time you dictate. Click Allow.
3. **fn / 🌐 key**: System Settings → Keyboard → set "Press 🌐 key to" to **Do Nothing**. Otherwise macOS opens the emoji picker. You can also pick Right ⌥ as the dictation key in Settings.
4. Ollama has to be running for AI edits (`ollama serve`). If it isn't, LocalFlow falls back to rule-based cleanup.

## How to use

| Action | How |
|---|---|
| Dictate | Hold **fn**, speak, release |
| Hands-free | **Double-tap fn**, speak as long as you like, tap fn again to finish |
| Cancel | **Esc** while recording |
| Command Mode | Select text, hold **fn + Control**, say "make this more formal" / "translate to Spanish" / "turn into bullets". With nothing selected, it writes new text ("draft a reply saying I'm running late") |
| Paste last transcript | Menu bar ◉ → Paste last transcript |
| Notetaker | Menu bar → Start Notetaker. Stopping it gives you a summary, decisions, action items and the transcript |
| Dashboard | Menu bar → Open Dashboard… (http://127.0.0.1:8765) |

## Features

- **Works in any app**: it pastes at the cursor and puts your clipboard back afterwards.
- **AI auto-edits**: removes filler words and stutters, applies self-corrections ("2pm, actually 3" → "3pm", "scratch that"), adds punctuation and paragraphs, formats lists, and handles spoken "new line" / "new paragraph".
- **Styles per app**: Formal, Casual or Very casual for personal messages, work chat, email and everything else. You can map any app by its bundle ID.
- **Personal dictionary**: steers Whisper's spelling and forces the exact casing. **Replacements** fix words it keeps mishearing. **Auto-learn**: correct a transcript in History and click "Save correction" to add new names to the dictionary.
- **Snippets**: say a cue such as "my calendar link" to insert saved text, either on its own or inside a sentence.
- **Command Mode**: rewrite, translate, shorten or reformat selected text by voice, or generate new text.
- **100+ languages**: auto-detects the language, or you can pin one (menu → Language).
- **Whisper mode**: boosts quiet or whispered speech so you can dictate in shared spaces.
- **Hands-free lock**, **Esc to cancel**, a floating **Flow bar** with a live waveform, and sound cues.
- **History and stats**: searchable history plus words dictated, WPM, minutes saved, day streak and latency.
- **Notetaker**: records meetings and voice memos with a rolling transcript and your own notes. It summarises topics, decisions and action items, offers **What did I miss?** during a meeting, and lets you **ask questions across all your meetings** with source citations.
- **Unlimited**, with no account and no internet connection needed after the models have downloaded.

## Models

- Speech: `mlx-community/whisper-large-v3-turbo` (default, about 1.5 GB, downloaded on first run). You can switch to large-v3 (more accurate) or small (faster) in Settings.
- Editing: any Ollama model. The default is `qwen2.5:7b`; `gemma3:4b` is faster.
- Meeting search: `nomic-embed-text`.

Measured on this Mac (M5): about 0.8 s to transcribe a 7-second clip and 0.4–1.5 s for the AI edit.

## Limitations compared with the hosted Wispr Flow

- **Notetaker records your microphone only.** To capture the other people on a call, route system audio in with a loopback device such as BlackHole and pick it as the microphone in Settings.
- macOS only. There are no iPhone, Android or Windows apps, no cloud sync, and no team features (shared dictionaries, SSO, admin tools).
- The model can't see the text field you're typing into, so it doesn't use that context for spelling.

## Files

- `localflow/`: the app. `app.py` is the menu bar and dictation flow, `hotkey.py` the fn/modifier event tap, `audio.py` microphone capture, `stt.py` Whisper, `editor.py` AI edits, snippets, dictionary and Command Mode, `notetaker.py` meetings, `dashboard.py` with `static/index.html` the local web UI, `overlay.py` the Flow bar.
- Data: `~/Library/Application Support/LocalFlow/` (settings.json, localflow.db, recordings/)
- Log: `~/Library/Logs/LocalFlow.log`

## License

MIT. See [LICENSE](LICENSE).
