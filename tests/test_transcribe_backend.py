import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from clipclipskill.transcribe import transcribe_audio


class TranscribeBackendTests(unittest.TestCase):
    def test_transcribe_audio_allows_stub_fallback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = Path(tmpdir) / "audio.wav"
            output_dir = Path(tmpdir) / "transcript"
            audio_path.write_bytes(b"stub")
            with patch("clipclipskill.transcribe.transcribe_with_faster_whisper", side_effect=RuntimeError("boom")):
                outputs = transcribe_audio(
                    audio_path,
                    output_dir,
                    template_id="solo_course",
                    language_hint="zh",
                    allow_stub_fallback=True,
                )
            self.assertTrue(Path(outputs["segments"]).exists())
            payload = Path(outputs["segments"]).read_text(encoding="utf-8")
            self.assertIn("stub-whisper", payload)


if __name__ == "__main__":
    unittest.main()
