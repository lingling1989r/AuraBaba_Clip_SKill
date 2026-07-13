import tempfile
import unittest
from pathlib import Path
from unittest import mock

from clipclipskill.ops_copy import build_full_article, build_podcast_headline, build_publish_copy, build_structured_title, write_full_article_assets


class OpsCopyTests(unittest.TestCase):
    def test_build_structured_title_is_stable_for_same_input(self):
        first = build_structured_title("podcast_interview", "招人成本越来越高", "招人成本越来越高")
        second = build_structured_title("podcast_interview", "招人成本越来越高", "招人成本越来越高")

        self.assertEqual(first, second)
        self.assertNotEqual(first, "招人成本越来越高")

    def test_build_publish_copy_uses_structured_headline(self):
        payload = build_publish_copy("solo_course", "利润越做越薄", "利润越做越薄")

        self.assertEqual(payload["headline"], build_structured_title("solo_course", "利润越做越薄", "利润越做越薄"))
        self.assertIn("利润越做越薄", payload["description"])

    def test_build_podcast_headline_adds_lane_and_guest_suffix(self):
        headline = build_podcast_headline(
            "podcast_interview",
            "AI员工与职场危机",
            "你的下一位同事可能是AI",
            guest_name="李想",
        )

        self.assertEqual(headline, "你的下一位同事可能是AI｜AI员工与职场危机 | 对话李想")

    def test_build_publish_copy_uses_podcast_headline_format_when_guest_exists(self):
        payload = build_publish_copy(
            "podcast_interview",
            "AI企业服务",
            "AI抢了你的工作吗",
            guest_name="王川",
        )

        self.assertEqual(payload["headline"], "AI抢了你的工作吗｜AI企业服务 | 对话王川")
        self.assertEqual(payload["platform_variants"]["xiaohongshu"]["title"], payload["headline"])

    def test_build_full_article_merges_same_speaker_and_followup_questions(self):
        article = build_full_article(
            job_id="job-1",
            title="一场很长的访谈",
            template_id="podcast_interview",
            transcript_text="",
            utterances=[
                {"speaker": "主持人", "text": "先聊聊你为什么开始做这件事？"},
                {"speaker": "主持人", "text": "当时最大的触发点是什么？"},
                {"speaker": "嘉宾", "text": "一开始是因为看到了行业里很明显的缺口。"},
                {"speaker": "嘉宾", "text": "后来我发现这不是一个短期问题，所以决定长期投入。"},
                {"speaker": "主持人", "text": "那你们后来是怎么验证方向的？"},
                {"speaker": "嘉宾", "text": "我们先找到了第一批种子用户反复访谈。"},
            ],
            host_name="小李",
            guest_name="老王",
        )

        self.assertEqual(article["host_name"], "小李")
        self.assertEqual(article["guest_name"], "老王")
        self.assertEqual(len(article["sections"]), 2)
        self.assertIn("为什么开始做这件事", article["sections"][0]["question"])
        self.assertIn("最大的触发点", article["sections"][0]["question"])
        self.assertEqual(len(article["sections"][0]["answers"]), 1)
        self.assertIn("长期投入", article["sections"][0]["answers"][0]["text"])

    def test_build_full_article_renders_header_and_summary(self):
        article = build_full_article(
            job_id="job-2",
            title="AI 创业访谈",
            template_id="podcast_interview",
            transcript_text="",
            utterances=[
                {"speaker": "主持人", "text": "你怎么看今年的行业变化？"},
                {"speaker": "嘉宾", "text": "我觉得最大的变化是大家开始重视交付结果。"},
            ],
            host_name="阿青",
            guest_name="周周",
        )

        markdown = article["markdown"]
        self.assertIn("整理人：傲雪（vx:aoxueluoluo）", markdown)
        self.assertIn("主持人：阿青", markdown)
        self.assertIn("嘉宾：周周", markdown)
        self.assertIn("## 导读", markdown)
        self.assertIn("这篇完整版访谈主要讲了", markdown)

    def test_write_full_article_assets_writes_markdown_and_docx(self):
        article = build_full_article(
            job_id="job-3",
            title="完整版整理",
            template_id="podcast_interview",
            transcript_text="完整转写文本",
            utterances=[],
            host_name="主持人A",
            guest_name="嘉宾B",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            def write_stub(markdown_path: Path, output_path: Path) -> None:
                output_path.write_text(markdown_path.read_text(encoding="utf-8"), encoding="utf-8")

            with mock.patch("clipclipskill.ops_copy._write_docx_from_markdown", side_effect=write_stub), mock.patch(
                "clipclipskill.ops_copy._write_pdf_from_markdown", side_effect=write_stub
            ):
                assets = write_full_article_assets(Path(temp_dir), article)

            self.assertTrue(assets["json"].exists())
            self.assertTrue(assets["md"].exists())
            self.assertTrue(assets["docx"].exists())
            self.assertTrue(assets["pdf"].exists())


if __name__ == "__main__":
    unittest.main()
