"""本地 TTS 模型注册表与下载管理器测试。

规则来源：.claude/rules/04-tts.md（免费可商用、模型目录不入 Git）。
"""
import io
import tarfile

import pytest

from tts.local.model_manager import (
    ModelManager,
    find_model,
    AVAILABLE_MODELS,
)


class FakeFetcher:
    """注入式下载器：模拟 download_file / list_repo_files。"""

    def __init__(self, archives: dict[str, bytes] | None = None, fail_hf: bool = False):
        self.archives = archives or {}
        self.fail_hf = fail_hf
        self.downloaded: list[str] = []

    def download_file(self, url: str, dest, progress=None) -> None:
        if self.fail_hf and url not in self.archives:
            raise OSError(f"模拟 hf 源失败: {url}")
        if url in self.archives:
            data = self.archives[url]
        else:
            data = b"fake:" + url.encode()
        dest.write_bytes(data)
        if progress is not None:
            progress(len(data), len(data))
        self.downloaded.append(url)

    def list_repo_files(self, repo: str) -> list[str]:
        if "melo" in repo:
            return [
                ".gitattributes",
                "model.onnx",
                "tokens.txt",
                "lexicon.txt",
                "date.fst",
                "number.fst",
                "phone.fst",
                "new_heteronym.fst",
                "dict/jieba.dict.utf8",
            ]
        if "kokoro" in repo:
            return [
                "model.onnx",
                "tokens.txt",
                "voices.bin",
                "lexicon-zh.txt",
                "espeak-ng-data/cmn_dict",
                "dict/jieba.dict.utf8",
            ]
        return []


def make_tar(member_dir: str, files: dict[str, str]) -> bytes:
    """内存中构造一个 tar.bz2，顶层目录为 member_dir。"""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:bz2") as tar:
        for rel, content in files.items():
            data = content.encode()
            info = tarfile.TarInfo(name=f"{member_dir}/{rel}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


# ── 注册表 ──


def test_registry_has_two_commercial_models():
    """注册表应包含轻量与中量两个免费可商用模型。"""
    ids = {m.model_id for m in AVAILABLE_MODELS}
    assert ids == {"vits-melo-tts-zh_en", "kokoro-multi-lang-v1_1"}


def test_registry_models_have_permissive_licenses():
    """两个模型的许可必须为 MIT / Apache-2.0（免费可商用）。"""
    licenses = {m.model_id: m.license for m in AVAILABLE_MODELS}
    assert licenses["vits-melo-tts-zh_en"] == "MIT"
    assert licenses["kokoro-multi-lang-v1_1"] == "Apache-2.0"


def test_find_model_returns_none_for_unknown():
    assert find_model("no-such-model") is None
    assert find_model("kokoro-multi-lang-v1_1") is not None


# ── 下载：archive 源（GitHub release tar.bz2）──


def test_download_from_archive_extracts_and_validates(tmp_path):
    melo = find_model("vits-melo-tts-zh_en")
    tar_bytes = make_tar(
        "vits-melo-tts-zh_en",
        {rel: f"content:{rel}" for rel in melo.required_files},
    )
    fetcher = FakeFetcher(archives={melo.sources[0].url: tar_bytes})
    manager = ModelManager(tmp_path, fetcher=fetcher)

    progress_calls: list[tuple[int, int | None]] = []
    path = manager.download(
        melo, progress=lambda done, total: progress_calls.append((done, total))
    )

    assert (path / "model.onnx").read_text() == "content:model.onnx"
    assert manager.is_downloaded(melo)
    assert progress_calls, "应报告下载进度"


def test_download_from_hf_repo_falls_back_when_archive_fails(tmp_path):
    """archive 源失败（内容为空/损坏）时应回退到 hf-mirror 按文件下载。"""
    melo = find_model("vits-melo-tts-zh_en")
    # archive 源给出损坏内容
    fetcher = FakeFetcher(archives={melo.sources[0].url: b"not-a-tar"})
    manager = ModelManager(tmp_path, fetcher=fetcher)

    path = manager.download(melo)

    assert (path / "model.onnx").exists()
    assert (path / "dict" / "jieba.dict.utf8").exists()
    # 至少调用过一次 hf 源的文件下载
    assert any("melo" in u and ".onnx" in u for u in fetcher.downloaded)


def test_download_archive_missing_required_file_cleans_up(tmp_path):
    """所有源均失败（压缩包缺文件 + hf 源不可用）时应报错并清理残留目录。"""
    melo = find_model("vits-melo-tts-zh_en")
    tar_bytes = make_tar(
        "vits-melo-tts-zh_en",
        {"model.onnx": "ONNX"},  # 缺 tokens.txt / lexicon.txt
    )
    fetcher = FakeFetcher(archives={melo.sources[0].url: tar_bytes}, fail_hf=True)
    manager = ModelManager(tmp_path, fetcher=fetcher)

    with pytest.raises(RuntimeError):
        manager.download(melo)

    assert not manager.is_downloaded(melo)
    # 不残留 .tmp / .extract 中间目录
    leftovers = [p.name for p in tmp_path.iterdir()]
    assert leftovers == [], f"应无残留中间文件: {leftovers}"


def test_all_sources_have_hf_fallback():
    """每个模型都应有 hf-mirror 回退源（应对 GitHub 不可达）。"""
    for m in AVAILABLE_MODELS:
        assert any(s.kind == "hf_repo" for s in m.sources)


# ── is_downloaded ──


def test_is_downloaded_false_when_missing(tmp_path):
    melo = find_model("vits-melo-tts-zh_en")
    manager = ModelManager(tmp_path)
    assert not manager.is_downloaded(melo)
