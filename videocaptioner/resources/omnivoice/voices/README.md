# Fixed AI voice references

These four references were synthesized specifically for VideoCaptioner with the
pinned OmniVoice model. They do not use a human speaker recording or BetterBox's
voice files. `catalog.json` records the model/code revisions, generation settings,
original generic script and SHA-256 of each mono PCM16 24 kHz WAV.

The labels identify samples, not guaranteed accents or subjective voice quality.
The bundled samples are used as reusable voice-cloning prompts for subsequent
utterances. The existing OmniVoice/audio-tokenizer component licenses still apply;
this folder does not relicense those components.

Do not replace an existing WAV without updating its hash and rechecking the voice.
Private user references belong in the application data voice library, not here.
