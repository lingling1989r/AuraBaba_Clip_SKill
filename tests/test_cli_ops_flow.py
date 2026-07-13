import tempfile
import unittest
from pathlib import Path
from unittest import mock

from clipclipskill import cli
from clipclipskill.ops_copy import build_podcast_headline
from clipclipskill.status import build_initial_status, mark_artifact, save_status, transition_status
from clipclipskill.workspace import create_job_workspace, read_json, write_json


class CliOpsFlowTests(unittest.TestCase):
    def test_cmd_ops_registers_full_article_artifacts(self):
        workspace = create_job_workspace("ops-full-article")
        status = build_initial_status(
            job_id=workspace.job_id,
            source_kind="local",
            input_video_path="/tmp/video.mp4",
            source_sha256="abc123",
            origin_path="/tmp/video.mp4",
            origin_url=None,
            platform=None,
            template_id="podcast_interview",
            length_mode="topic_complete",
            target_seconds=None,
            transcription_mode="whisper",
            diarization_mode="auto",
            language_hint="auto",
        )
        status = mark_artifact(status, "transcript_text", "transcript/transcript.txt")
        status = mark_artifact(status, "utterances", "transcript/utterances.json")
        status = transition_status(status, "probed")
        status = transition_status(status, "awaiting_template_confirmation")
        status = transition_status(status, "confirmed_for_transcription")
        status = transition_status(status, "transcribing")
        status = transition_status(status, "transcribed")
        status = transition_status(status, "analysis_ready")
        status = transition_status(status, "awaiting_plan_confirmation")
        status = transition_status(status, "approved_for_render")
        status = transition_status(status, "rendering")
        status = transition_status(status, "ops_generating")
        save_status(workspace.status_path, status)

        (workspace.transcript_dir / "transcript.txt").write_text("完整访谈文本", encoding="utf-8")
        write_json(
            workspace.transcript_dir / "utterances.json",
            {
                "utterances": [
                    {"speaker": "主持人", "text": "你为什么开始做这个项目？"},
                    {"speaker": "嘉宾", "text": "因为我看到很多用户有真实需求。"},
                ]
            },
        )
        write_json(
            workspace.planning_dir / "clip_plan.v1.json",
            {
                "template": "podcast_interview",
                "clips": [
                    {
                        "sequence": 1,
                        "title": "第一条剪辑标题",
                        "topic": "用户需求",
                        "output_stem": "用户需求_001",
                    }
                ],
            },
        )

        expected_headline = build_podcast_headline(
            "podcast_interview",
            "用户需求",
            "第一条剪辑标题",
            guest_name="老周",
        )

        def write_stub(ops_dir: Path, rows: list[dict]):
            self.assertEqual(rows[0]["headline"], expected_headline)
            (ops_dir / "publish_copy.json").write_text("{}", encoding="utf-8")
            (ops_dir / "publish_copy.md").write_text("# copy\n", encoding="utf-8")
            return {"json": ops_dir / "publish_copy.json", "md": ops_dir / "publish_copy.md"}

        def article_stub(ops_dir: Path, article: dict):
            paths = {
                "json": ops_dir / "full_article.json",
                "md": ops_dir / "full_article.md",
                "docx": ops_dir / "full_article.docx",
                "pdf": ops_dir / "full_article.pdf",
            }
            for path in paths.values():
                path.write_text("artifact", encoding="utf-8")
            return paths

        with mock.patch.object(cli, "write_publish_copy", side_effect=write_stub) as publish_mock, mock.patch.object(
            cli, "write_full_article_assets", side_effect=article_stub
        ):
            result = cli.cmd_ops(
                type(
                    "Args",
                    (),
                    {
                        "job_id": workspace.job_id,
                        "host_name": "阿青",
                        "guest_name": "老周",
                        "article_title": "完整版标题",
                    },
                )()
            )

        self.assertEqual(publish_mock.call_args.args[0], workspace.ops_dir)
        self.assertEqual(publish_mock.call_args.args[1][0]["headline"], expected_headline)

        self.assertEqual(result, 0)
        saved = read_json(workspace.status_path)
        self.assertEqual(saved["phase"], "validating")
        self.assertEqual(saved["artifacts"]["publish_manifest"], "ops/publish_manifest.json")
        self.assertEqual(saved["artifacts"]["full_article_markdown"], "ops/full_article.md")
        self.assertEqual(saved["artifacts"]["full_article_docx"], "ops/full_article.docx")
        self.assertEqual(saved["artifacts"]["full_article_pdf"], "ops/full_article.pdf")


if __name__ == "__main__":
    unittest.main()
