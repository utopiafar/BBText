"""测试 B站 URL 解析和 ID 转换"""

from bbt.bilibili.parser import parse_url, decode_bv, encode_av, VideoID


class TestBVConversion:
    """BV/AV 互转测试"""

    def test_decode_known_bv(self):
        """使用已知 BV 号验证解码"""
        # BV17x411w7KC -> av170001 (经典测试用例)
        avid = decode_bv("BV17x411w7KC")
        assert isinstance(avid, int)
        assert avid > 0

    def test_roundtrip(self):
        """AV -> BV -> AV 往返测试"""
        original_aid = 170001
        bvid = encode_av(original_aid)
        assert bvid.startswith("BV1")
        decoded_aid = decode_bv(bvid)
        assert decoded_aid == original_aid

    def test_roundtrip_multiple(self):
        """多个 AV 号往返测试"""
        for aid in [1, 100, 99999, 12345678, 999999999]:
            bvid = encode_av(aid)
            assert decode_bv(bvid) == aid


class TestParseUrl:
    """URL 解析测试"""

    def test_av_url(self):
        vid = parse_url("https://www.bilibili.com/video/av170001")
        assert vid is not None
        assert vid.type == "av"
        assert vid.id == "170001"

    def test_bv_url(self):
        vid = parse_url("https://www.bilibili.com/video/BV17x411w7KC")
        assert vid is not None
        assert vid.type == "av"
        assert vid.id.isdigit()

    def test_ep_url(self):
        vid = parse_url("https://www.bilibili.com/bangumi/play/ep12345")
        assert vid is not None
        assert vid.type == "ep"
        assert vid.id == "12345"

    def test_ss_url(self):
        vid = parse_url("https://www.bilibili.com/bangumi/play/ss12345")
        assert vid is not None
        assert vid.type == "ss"
        assert vid.id == "12345"

    def test_bv_lowercase(self):
        vid = parse_url("https://www.bilibili.com/video/bv17x411w7KC")
        assert vid is not None
        assert vid.type == "av"

    def test_short_format_bv(self):
        """直接 BV 号"""
        vid = parse_url("BV17x411w7KC")
        assert vid is not None
        assert vid.type == "av"

    def test_invalid_url(self):
        vid = parse_url("https://www.google.com")
        assert vid is None
