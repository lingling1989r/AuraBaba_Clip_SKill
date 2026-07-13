import tempfile
import unittest
from pathlib import Path
from unittest import mock

from clipclipskill.render import render_clip


class RenderLayoutTests(unittest.TestCase):
    def test_render_clip_writes_flat_files_named_by_topic(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            clips_dir = Path(temp_dir) / "clips"
            artifact_dir = Path(temp_dir) / "planning_package" / "clip_artifacts"
            source_video = Path(temp_dir) / "source.mp4"
            source_video.write_text("video", encoding="utf-8")

            assets = render_clip(
                source_video,
                clips_dir,
                artifact_dir,
                sequence=1,
                title="用户需求",
                stem="用户需求_001",
                start_sec=0.0,
                end_sec=12.0,
            )

            self.assertEqual(Path(assets["clip"]).name, "用户需求_001.mp4")
            self.assertEqual(Path(assets["subtitle"]).name, "用户需求_001.srt")
            self.assertEqual(Path(assets["manifest"]).name, "用户需求_001.json")
            self.assertEqual(Path(assets["clip"]).parent, clips_dir)
            self.assertEqual(Path(assets["subtitle"]).parent, artifact_dir)
            self.assertEqual(Path(assets["manifest"]).parent, artifact_dir)

    def test_render_clip_uses_quicktime_friendly_ffmpeg_settings(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            clips_dir = Path(temp_dir) / "clips"
            artifact_dir = Path(temp_dir) / "planning_package" / "clip_artifacts"
            source_video = Path(temp_dir) / "source.mp4"
            source_video.write_text("video", encoding="utf-8")

            with mock.patch("clipclipskill.render.shutil.which", return_value="/usr/bin/ffmpeg"), mock.patch(
                "clipclipskill.render.subprocess.run"
            ) as run_mock:
                render_clip(
                    source_video,
                    clips_dir,
                    artifact_dir,
                    sequence=1,
                    title="用户需求",
                    stem="用户需求_001",
                    start_sec=3.0,
                    end_sec=12.0,
                )

            command = run_mock.call_args.args[0]
            self.assertIn("-c:v", command)
            self.assertIn("libx264", command)
            self.assertIn("-pix_fmt", command)
            self.assertIn("yuv420p", command)
            self.assertIn("-movflags", command)
            self.assertIn("+faststart", command)
            self.assertIn("-c:a", command)
            self.assertIn("aac", command)
            self.assertNotIn("copy", command)


if __name__ == "__main__":
    unittest.main()
