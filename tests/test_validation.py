import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from clipclipskill.validation import validate_clips, validate_publish_outputs


class ValidationTests(unittest.TestCase):
    def test_validate_publish_outputs_rejects_process_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            publish_copy_path = base / "publish_copy.json"
            article_markdown_path = base / "full_article.md"
            publish_copy_path.write_text(
                json.dumps(
                    {
                        "clips": [
                            {
                                "sequence": 1,
                                "headline": "AI抢了你的工作吗｜AI职场危机 | 对话李想 Vol 03",
                                "short_hook": "30秒看懂：用户需求",
                                "description": "这里包含 thinking 过程，不应该出现在交付文案里。",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            article_markdown_path.write_text("# 用户需求\n正常内容", encoding="utf-8")

            report = validate_publish_outputs(
                clip_plan={"clips": [{"topic": "用户需求"}]},
                publish_copy_path=publish_copy_path,
                article_markdown_path=article_markdown_path,
            )

        self.assertFalse(report["passed"])
        self.assertTrue(any("thinking" in issue for issue in report["issues"]))

    def test_validate_publish_outputs_rejects_long_headline(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            publish_copy_path = base / "publish_copy.json"
            article_markdown_path = base / "full_article.md"
            publish_copy_path.write_text(
                json.dumps(
                    {
                        "clips": [
                            {
                                "sequence": 1,
                                "headline": "你的下一位同事可能是AI还是外包还是系统还是机器人还是分身还是数字员工｜AI职场危机与企业焦虑升级版深聊以及传统团队转型漫长阵痛 | 对话李想 Vol 123456789",
                                "short_hook": "30秒看懂：利润越做越薄",
                                "description": "这条短视频围绕利润越做越薄展开，适合做独立传播。",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            article_markdown_path.write_text("# 利润越做越薄\n正常内容", encoding="utf-8")

            report = validate_publish_outputs(
                clip_plan={"clips": [{"topic": "利润越做越薄"}]},
                publish_copy_path=publish_copy_path,
                article_markdown_path=article_markdown_path,
            )

        self.assertFalse(report["passed"])
        self.assertTrue(any("headline length" in issue for issue in report["issues"]))

    def test_validate_publish_outputs_rejects_technical_jargon_headline(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            publish_copy_path = base / "publish_copy.json"
            article_markdown_path = base / "full_article.md"
            publish_copy_path.write_text(
                json.dumps(
                    {
                        "clips": [
                            {
                                "sequence": 1,
                                "headline": "我靠提示词把招人成本压下来了",
                                "short_hook": "30秒看懂：招人成本高",
                                "description": "这条短视频围绕招人成本高展开，适合做独立传播。",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            article_markdown_path.write_text("# 招人成本高\n正常内容", encoding="utf-8")

            report = validate_publish_outputs(
                clip_plan={"clips": [{"topic": "招人成本高"}]},
                publish_copy_path=publish_copy_path,
                article_markdown_path=article_markdown_path,
            )

        self.assertFalse(report["passed"])
        self.assertTrue(any("technical jargon" in issue for issue in report["issues"]))

    def test_validate_publish_outputs_allows_ai_podcast_headline(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            publish_copy_path = base / "publish_copy.json"
            article_markdown_path = base / "full_article.md"
            publish_copy_path.write_text(
                json.dumps(
                    {
                        "clips": [
                            {
                                "sequence": 1,
                                "headline": "AI抢了你的工作吗｜用户需求 | 对话李想 Vol 03",
                                "short_hook": "30秒看懂：用户需求",
                                "description": "这条短视频围绕用户需求展开，适合做独立传播。",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            article_markdown_path.write_text("# 用户需求\n正常内容", encoding="utf-8")

            report = validate_publish_outputs(
                clip_plan={"clips": [{"topic": "用户需求"}]},
                publish_copy_path=publish_copy_path,
                article_markdown_path=article_markdown_path,
            )

        self.assertTrue(report["passed"])
        self.assertEqual(report["issues"], [])

    def test_validate_clips_uses_ffprobe_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            clips_dir = Path(temp_dir)
            clip_path = clips_dir / "用户需求_001.mp4"
            clip_path.write_text("video", encoding="utf-8")

            with mock.patch("clipclipskill.validation._probe_video_stream") as probe_mock:
                probe_mock.return_value = {
                    "status": "ok",
                    "message": "ok",
                    "video_stream_count": 1,
                    "avg_frame_rate": 25.0,
                    "duration_sec": 12.0,
                    "has_audio": True,
                    "video_codec": "h264",
                    "audio_codec": "aac",
                    "pixel_format": "yuv420p",
                    "video_duration_sec": 12.0,
                    "audio_duration_sec": 12.0,
                    "estimated_speed_ratio": 1.0,
                }
                report = validate_clips(
                    clips_dir=clips_dir,
                    clip_plan={"clips": [{"output_stem": "用户需求_001"}]},
                )

        self.assertTrue(report["passed"])
        self.assertEqual(report["issues"], [])

    def test_validate_clips_rejects_quicktime_incompatible_export(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            clips_dir = Path(temp_dir)
            clip_path = clips_dir / "用户需求_001.mp4"
            clip_path.write_text("video", encoding="utf-8")

            with mock.patch("clipclipskill.validation._probe_video_stream") as probe_mock:
                probe_mock.return_value = {
                    "status": "ok",
                    "message": "ok",
                    "video_stream_count": 1,
                    "avg_frame_rate": 25.0,
                    "duration_sec": 12.0,
                    "has_audio": True,
                    "video_codec": "hevc",
                    "audio_codec": "mp3",
                    "pixel_format": "yuv444p",
                    "video_duration_sec": 12.0,
                    "audio_duration_sec": 11.3,
                    "estimated_speed_ratio": 1.0,
                }
                report = validate_clips(
                    clips_dir=clips_dir,
                    clip_plan={"clips": [{"output_stem": "用户需求_001"}]},
                )

        self.assertFalse(report["passed"])
        self.assertTrue(any("QuickTime" in issue for issue in report["issues"]))
        self.assertTrue(any("pixel format" in issue for issue in report["issues"]))
        self.assertTrue(any("duration drift" in issue for issue in report["issues"]))

    def test_validate_clips_rejects_speed_anomaly(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            clips_dir = Path(temp_dir)
            clip_path = clips_dir / "用户需求_001.mp4"
            clip_path.write_text("video", encoding="utf-8")

            with mock.patch("clipclipskill.validation._probe_video_stream") as probe_mock:
                probe_mock.return_value = {
                    "status": "ok",
                    "message": "ok",
                    "video_stream_count": 1,
                    "avg_frame_rate": 25.0,
                    "duration_sec": 12.0,
                    "has_audio": True,
                    "video_codec": "h264",
                    "audio_codec": "aac",
                    "pixel_format": "yuv420p",
                    "video_duration_sec": 18.0,
                    "audio_duration_sec": 18.0,
                    "estimated_speed_ratio": 1.5,
                }
                report = validate_clips(
                    clips_dir=clips_dir,
                    clip_plan={"clips": [{"output_stem": "用户需求_001"}]},
                )

        self.assertFalse(report["passed"])
        self.assertTrue(any("playback speed" in issue for issue in report["issues"]))


if __name__ == "__main__":
    unittest.main()
