import unittest

from clipclipskill.analysis import build_utterances
from clipclipskill.segment import build_segment_candidates


class AnalysisPipelineTests(unittest.TestCase):
    def test_build_utterances_applies_speaker_overlap(self):
        segments = [
            {"id": 1, "start": 0.0, "end": 10.0, "text": "主持人提问。", "avg_logprob": -0.2, "no_speech_prob": 0.02},
            {"id": 2, "start": 10.0, "end": 30.0, "text": "嘉宾完整回答这个问题。", "avg_logprob": -0.2, "no_speech_prob": 0.02},
        ]
        diarization = [
            {"start": 0.0, "end": 9.0, "speaker": "SPEAKER_00"},
            {"start": 9.0, "end": 30.0, "speaker": "SPEAKER_01"},
        ]
        utterances = build_utterances(segments, diarization)
        self.assertEqual(utterances[0]["speaker"], "SPEAKER_00")
        self.assertEqual(utterances[1]["speaker"], "SPEAKER_01")

    def test_segment_candidates_merge_utterances(self):
        utterances = [
            {"utterance_id": "utt_0001", "start": 0.0, "end": 20.0, "text": "第一句还没讲完", "speaker": "SPEAKER_00", "avg_logprob": -0.2, "no_speech_prob": 0.01},
            {"utterance_id": "utt_0002", "start": 20.0, "end": 48.0, "text": "现在把关键结论讲完整。", "speaker": "SPEAKER_00", "avg_logprob": -0.2, "no_speech_prob": 0.01},
            {"utterance_id": "utt_0003", "start": 48.0, "end": 90.0, "text": "另一个完整话题也结束了。", "speaker": "SPEAKER_01", "avg_logprob": -0.2, "no_speech_prob": 0.01},
        ]
        candidates = build_segment_candidates(
            utterances,
            template_id="podcast_interview",
            length_mode="topic_complete",
            target_seconds=None,
        )
        self.assertLess(len(candidates), len(utterances))
        self.assertEqual(candidates[0]["source_utterance_ids"], ["utt_0001", "utt_0002"])


if __name__ == "__main__":
    unittest.main()
