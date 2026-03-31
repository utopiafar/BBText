"""测试下载模块核心逻辑（不发真实请求）"""

from bbt.bilibili.api import BilibiliClient, AudioTrack, CODEC_MAP, AUDIO_QUALITY_PRIORITY


class TestSelectBestAudio:
    """音频流选择测试"""

    def _make_track(self, audio_id: str, bandwidth: int = 128) -> AudioTrack:
        return AudioTrack(
            id=audio_id,
            quality=audio_id,
            bandwidth=bandwidth,
            codec="M4A",
            duration=300,
            url="https://example.com/audio.m4a",
        )

    def test_empty(self):
        client = BilibiliClient()
        assert client.select_best_audio([]) is None

    def test_prefers_flac(self):
        """优先选择 Hi-Res FLAC"""
        tracks = [
            self._make_track("30216"),  # 64K
            self._make_track("30232"),  # 132K
            self._make_track("30251"),  # FLAC
        ]
        client = BilibiliClient()
        best = client.select_best_audio(tracks)
        assert best is not None
        assert best.id == "30251"

    def test_prefers_higher_quality(self):
        """没有 FLAC 时选最高质量"""
        tracks = [
            self._make_track("30216"),  # 64K
            self._make_track("30232"),  # 132K
        ]
        client = BilibiliClient()
        best = client.select_best_audio(tracks)
        assert best is not None
        assert best.id == "30232"

    def test_fallback_bandwidth(self):
        """未知 ID 时按带宽选"""
        tracks = [
            self._make_track("99999", bandwidth=64),
            self._make_track("99998", bandwidth=320),
        ]
        client = BilibiliClient()
        best = client.select_best_audio(tracks)
        assert best is not None
        assert best.bandwidth == 320


class TestCodecMap:
    def test_known_codecs(self):
        assert CODEC_MAP["mp4a.40.2"] == "M4A"
        assert CODEC_MAP["ec-3"] == "E-AC-3"
        assert CODEC_MAP["fLaC"] == "FLAC"
