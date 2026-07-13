import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from clipclipskill import cli
from clipclipskill.status import build_initial_status, save_status
from clipclipskill.workspace import create_job_workspace, read_json

ROOT = Path(__file__).resolve().parents[1]
CLI = [sys.executable, "-m", "clipclipskill.cli"]


class CliUrlFlowTests(unittest.TestCase):
    def test_start_job_with_url_persists_url_source(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "src")
        with tempfile.TemporaryDirectory() as workspace_dir:
            result = subprocess.run(
                CLI
                + [
                    "--workspace-dir",
                    workspace_dir,
                    "start-job",
                    "--url",
                    "https://youtu.be/example",
                    "--template",
                    "podcast_interview",
                ],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=True,
            )
            payload = json.loads(result.stdout)
            status = read_json(Path(payload["status_path"]))
            self.assertEqual(status["source"]["kind"], "url")
            self.assertEqual(status["source"]["origin_url"], "https://youtu.be/example")
            self.assertEqual(status["source"]["platform"], "youtube")
            self.assertEqual(status["source"]["download_status"], "pending")
            self.assertIsNone(status["source"]["input_video_path"])
            self.assertTrue(str(Path(payload["status_path"])).startswith(str(Path(workspace_dir).resolve())))

    def test_start_job_rejects_unsupported_url(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "src")
        result = subprocess.run(
            CLI
            + [
                "start-job",
                "--url",
                "https://example.com/video",
                "--template",
                "podcast_interview",
            ],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("only YouTube and Bilibili URLs are supported", result.stderr)

    def test_start_job_requires_yt_dlp_for_url_input(self):
        args = cli.parse_args(["start-job", "--url", "https://youtu.be/example", "--template", "podcast_interview"])
        with mock.patch.object(
            cli,
            "detect_local_capabilities",
            return_value={
                "tools": {"ffmpeg": True, "ffprobe": True},
                "imports": {"faster_whisper": True, "pyannote_audio": False, "torch": False, "yt_dlp": False},
                "torch": {"available": False, "cuda_available": False},
                "system": {"cpu_count": 4, "memory_total_bytes": 8, "memory_available_bytes": 8, "disk_free_bytes": 8},
                "auth": {"has_hf_token": False},
                "input": {"audio_present": True},
            },
        ):
            with self.assertRaisesRegex(cli.StatusError, "yt-dlp is not installed"):
                cli._check_required_dependencies("start-job", args)

    def test_probe_records_failed_download(self):
        workspace = create_job_workspace("url-download-fail")
        status = build_initial_status(
            job_id=workspace.job_id,
            source_kind="url",
            input_video_path=None,
            source_sha256=None,
            origin_path=None,
            origin_url="https://youtu.be/example",
            platform="youtube",
            template_id="podcast_interview",
            length_mode="topic_complete",
            target_seconds=None,
            transcription_mode="whisper",
            diarization_mode="auto",
            language_hint="auto",
        )
        save_status(workspace.status_path, status)

        with mock.patch.object(cli, "detect_local_capabilities", return_value={"imports": {"yt_dlp": True}}), mock.patch.object(
            cli, "download_video_source", side_effect=RuntimeError("boom")
        ):
            with self.assertRaises(cli.StatusError):
                cli.cmd_probe(type("Args", (), {"job_id": workspace.job_id})())

        saved = read_json(workspace.status_path)
        self.assertEqual(saved["phase"], "failed")
        self.assertEqual(saved["source"]["download_status"], "pending")
        self.assertTrue(saved["errors"])
        self.assertIn("download failed: boom", saved["errors"][-1]["message"])

    def test_probe_reuses_downloaded_video_without_redownloading(self):
        workspace = create_job_workspace("url-download-reuse")
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as handle:
            handle.write(b"video-data")
            downloaded_path = Path(handle.name)

        status = build_initial_status(
            job_id=workspace.job_id,
            source_kind="url",
            input_video_path=None,
            source_sha256=None,
            origin_path=None,
            origin_url="https://youtu.be/example",
            platform="youtube",
            template_id="podcast_interview",
            length_mode="topic_complete",
            target_seconds=None,
            transcription_mode="whisper",
            diarization_mode="auto",
            language_hint="auto",
        )
        status["source"]["downloaded_video_path"] = str(downloaded_path)
        status["source"]["download_status"] = "completed"
        save_status(workspace.status_path, status)

        normalized = {
            "duration_sec": 12.5,
            "size_bytes": 1234,
            "audio": {"present": True},
        }
        profile = {
            "verdict": "ok",
            "asr_backend": "faster-whisper",
            "asr_model": "small",
            "device": "cpu",
            "compute_type": "int8",
            "language_hint": "auto",
            "diarization_enabled": False,
            "diarization_reason": "disabled",
            "warnings": [],
            "blocking_reasons": [],
            "resource_summary": {
                "cpu_count": 4,
                "memory_total_bytes": 8,
                "memory_available_bytes": 8,
                "disk_free_bytes": 8,
            },
        }
        estimate = {"total_estimated_minutes": 1, "step_eta_seconds": {"probe": 1}}
        capability_probe = {
            "tools": {"ffmpeg": True, "ffprobe": True},
            "imports": {"faster_whisper": True, "pyannote_audio": False, "torch": False, "yt_dlp": True},
            "torch": {"available": False, "cuda_available": False},
            "system": {
                "cpu_count": 4,
                "memory_total_bytes": 8,
                "memory_available_bytes": 8,
                "disk_free_bytes": 8,
            },
            "auth": {"has_hf_token": False},
            "input": {"audio_present": True},
        }

        try:
            with mock.patch.object(cli, "detect_local_capabilities", side_effect=[{"imports": {"yt_dlp": True}}, capability_probe]), mock.patch.object(
                cli, "download_video_source", side_effect=AssertionError("should not download")
            ), mock.patch.object(cli, "probe_video", return_value=normalized), mock.patch.object(
                cli, "select_execution_profile", return_value=profile
            ), mock.patch.object(cli, "estimate_processing_time", return_value=estimate):
                result = cli.cmd_probe(type("Args", (), {"job_id": workspace.job_id})())

            self.assertEqual(result, 0)
            saved = read_json(workspace.status_path)
            self.assertEqual(saved["phase"], "awaiting_template_confirmation")
            self.assertEqual(saved["source"]["input_video_path"], str(downloaded_path))
            self.assertEqual(saved["source"]["downloaded_video_path"], str(downloaded_path))
            self.assertEqual(saved["source"]["download_status"], "completed")
            self.assertEqual(saved["source"]["resolved_url"], "https://youtu.be/example")
        finally:
            downloaded_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
