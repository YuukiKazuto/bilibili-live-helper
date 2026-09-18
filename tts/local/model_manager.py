"""本地 TTS 模型注册表与下载管理器。

规则来源：.claude/rules/04-tts.md —— 模型必须免费可商用（MIT / Apache-2.0），
模型存储目录按 resolve_models_dir() 解析（见下方说明，用户偏好 models_dir 可覆盖）。

下载源设计为多源依次尝试：GitHub release 压缩包优先，hf-mirror 按文件下载回退
（GitHub 直连在国内网络经常不可达，hf-mirror.com 为 HuggingFace 国内镜像）。
"""
import logging
import os
import shutil
import sys
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int | None], None]

# 项目根目录（开发模式默认模型目录，已加入 .gitignore）
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
MODELS_DIR = ROOT_DIR / "models"

_APP_DIR_NAME = "bilibili-live-helper"


def _is_writable(dir_path: Path) -> bool:
    """探测目录可写（含创建）；只读目录返回 False。"""
    try:
        dir_path.mkdir(parents=True, exist_ok=True)
        probe = dir_path / ".write_probe"
        probe.touch()
        probe.unlink()
        return True
    except OSError:
        return False


def user_models_dir() -> Path:
    """用户数据目录下的模型目录（跨平台，安装到只读目录时也可写）。"""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / _APP_DIR_NAME / "models"


def resolve_models_dir(override: str = "") -> Path:
    """按 .claude/rules/04-tts.md「模型存储目录」解析模型目录：

    1. 用户偏好显式配置 models_dir → 直接使用；
    2. 开发模式（源码运行，未打包）→ 项目根 models/，便于调试；
    3. 打包后（sys.frozen）安装目录可写 → 便携版，下载到安装目录 models/；
    4. 安装目录只读（如 Program Files）→ 用户数据目录
       （Windows %LOCALAPPDATA%、macOS ~/Library/Application Support 等）。
    """
    if override:
        return Path(override)

    if not getattr(sys, "frozen", False):
        return MODELS_DIR  # 开发模式

    exe_dir = Path(sys.executable).resolve().parent
    if _is_writable(exe_dir):
        return exe_dir / "models"  # 便携版：安装目录可写
    return user_models_dir()

# 下载临时文件前缀（异常时清理，不污染模型目录）
_TMP_PREFIX = "."


@dataclass(frozen=True)
class ModelSource:
    """单一下载源：kind=archive（tar.bz2 单文件）或 hf_repo（按文件下载）。"""

    url: str
    kind: str  # "archive" | "hf_repo"


@dataclass(frozen=True)
class LocalModel:
    """一个可下载的本地语音模型（免费可商用，许可见 license 字段）。"""

    model_id: str            # 同时是磁盘上的目录名
    display_name: str
    license: str
    size_hint: str           # 给未来 UI 展示的体积提示
    engine: str              # sherpa-onnx 引擎类型："vits" | "kokoro"
    required_files: tuple[str, ...]   # 下载完成校验必需的文件（相对模型目录）
    config: dict[str, str]   # sherpa-onnx 配置项 → 模型目录内相对路径
    sources: tuple[ModelSource, ...]


# ── 模型注册表（免费可商用，许可已核实；来源：k2-fsa/sherpa-onnx 官方转换） ──
_MELO = LocalModel(
    model_id="vits-melo-tts-zh_en",
    display_name="MeloTTS 中英（轻量）",
    license="MIT",
    size_hint="约 170MB",
    engine="vits",
    required_files=(
        "model.onnx",
        "tokens.txt",
        "lexicon.txt",
        "date.fst",
        "number.fst",
        "phone.fst",
        "new_heteronym.fst",
        "dict/jieba.dict.utf8",
    ),
    config={
        "model": "model.onnx",
        "tokens": "tokens.txt",
        "lexicon": "lexicon.txt",
        "dict_dir": "dict",
        "rule_fsts": "date.fst,number.fst,phone.fst,new_heteronym.fst",
    },
    sources=(
        ModelSource(
            url="https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-melo-tts-zh_en.tar.bz2",
            kind="archive",
        ),
        ModelSource(
            url="https://hf-mirror.com/csukuangfj/vits-melo-tts-zh_en",
            kind="hf_repo",
        ),
    ),
)

_KOKORO = LocalModel(
    model_id="kokoro-multi-lang-v1_1",
    display_name="Kokoro 中英（音质优先）",
    license="Apache-2.0",
    size_hint="约 310MB",
    engine="kokoro",
    required_files=(
        "model.onnx",
        "tokens.txt",
        "voices.bin",
        "lexicon-zh.txt",
        "date-zh.fst",
        "number-zh.fst",
        "phone-zh.fst",
        "espeak-ng-data/phontab",
        "espeak-ng-data/cmn_dict",
        "dict/jieba.dict.utf8",
    ),
    config={
        "model": "model.onnx",
        "voices": "voices.bin",
        "tokens": "tokens.txt",
        "lexicon": "lexicon-zh.txt",
        "data_dir": "espeak-ng-data",
        "dict_dir": "dict",
        "rule_fsts": "date-zh.fst,number-zh.fst,phone-zh.fst",
    },
    sources=(
        ModelSource(
            url="https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/kokoro-multi-lang-v1_1.tar.bz2",
            kind="archive",
        ),
        ModelSource(
            url="https://hf-mirror.com/csukuangfj/kokoro-multi-lang-v1_1",
            kind="hf_repo",
        ),
    ),
)

AVAILABLE_MODELS: tuple[LocalModel, ...] = (_MELO, _KOKORO)

_MODELS_BY_ID = {m.model_id: m for m in AVAILABLE_MODELS}


def find_model(model_id: str) -> LocalModel | None:
    """按 id 查找模型；未知 id 返回 None。"""
    return _MODELS_BY_ID.get(model_id)


class Fetcher:
    """下载器接口（便于测试注入假实现）。"""

    def download_file(self, url: str, dest: Path, progress: ProgressCallback | None = None) -> None:
        raise NotImplementedError

    def list_repo_files(self, repo_url: str) -> list[str]:
        raise NotImplementedError


class RequestsFetcher(Fetcher):
    """基于 requests 的默认下载器（requests 已是项目依赖）。"""

    def download_file(self, url: str, dest: Path, progress: ProgressCallback | None = None) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with requests.get(url, stream=True, timeout=60) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("Content-Length") or 0) or None
            done = 0
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                    f.write(chunk)
                    done += len(chunk)
                    if progress is not None:
                        progress(done, total)

    def list_repo_files(self, repo_url: str) -> list[str]:
        """hf 镜像仓库文件列表：https://<host>/<owner>/<repo> → <host>/api/models/<owner>/<repo>。"""
        path = repo_url.rstrip("/").removeprefix("https://").removeprefix("http://")
        api_url = f"https://{path.split('/')[0]}/api/models/{'/'.join(path.split('/')[1:])}"
        resp = requests.get(api_url, timeout=30)
        resp.raise_for_status()
        return [s["rfilename"] for s in resp.json().get("siblings", [])]


class ModelManager:
    """模型下载与完整性校验：多源依次尝试，失败清理残留。"""

    # hf 按文件下载时跳过的仓库元文件与用不到的 int8 量化副本（节省一半流量）
    _HF_SKIP = {".gitattributes", "model.int8.onnx", "model.int8.onnx.tmp"}

    def __init__(self, models_dir: Path, fetcher: Fetcher | None = None) -> None:
        self.models_dir = Path(models_dir)
        self._fetcher = fetcher or RequestsFetcher()

    def model_dir(self, model: LocalModel) -> Path:
        return self.models_dir / model.model_id

    def is_downloaded(self, model: LocalModel) -> bool:
        """目录存在且所有必需文件齐全即视为可用。"""
        d = self.model_dir(model)
        return d.is_dir() and all((d / rel).is_file() for rel in model.required_files)

    def download(
        self,
        model: LocalModel,
        progress: ProgressCallback | None = None,
    ) -> Path:
        """下载模型，返回模型目录。逐个源尝试，全部失败抛 RuntimeError。"""
        if self.is_downloaded(model):
            return self.model_dir(model)

        last_err: Exception | None = None
        for source in model.sources:
            try:
                if source.kind == "archive":
                    self._download_archive(source.url, model, progress)
                else:
                    self._download_hf_repo(source.url, model, progress)
                return self.model_dir(model)
            except Exception as exc:  # noqa: BLE001 — 单源失败回退下一个源
                logger.warning("[本地TTS] 下载源失败(%s): %s", source.kind, exc)
                last_err = exc
            finally:
                self._cleanup(model)
        raise RuntimeError(f"模型 {model.model_id} 所有下载源均失败") from last_err

    # ── 内部实现 ──

    def _download_archive(self, url: str, model: LocalModel, progress: ProgressCallback | None) -> None:
        """下载 tar.bz2 压缩包 → 解压 → 校验必需文件 → 移入正式目录。"""
        self.models_dir.mkdir(parents=True, exist_ok=True)
        archive = self.models_dir / f"{_TMP_PREFIX}{model.model_id}.tar.tmp"
        staging = self.models_dir / f"{_TMP_PREFIX}{model.model_id}.extract"
        self._fetcher.download_file(url, archive, progress)

        staging.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive, "r:bz2") as tar:
            tar.extractall(staging, filter="data")

        # 压缩包内是单一顶层目录（与 model_id 同名）
        entries = [p for p in staging.iterdir() if p.is_dir()]
        if len(entries) != 1:
            raise RuntimeError(f"压缩包内顶层目录异常: {[p.name for p in staging.iterdir()]}")
        extracted = entries[0]

        missing = [rel for rel in model.required_files if not (extracted / rel).is_file()]
        if missing:
            raise RuntimeError(f"压缩包缺必需文件: {missing}")

        extracted.rename(self.model_dir(model))
        shutil.rmtree(staging, ignore_errors=True)

    def _download_hf_repo(self, repo_url: str, model: LocalModel, progress: ProgressCallback | None) -> None:
        """hf 镜像按文件下载整个仓库到模型目录，完成后校验。"""
        dest = self.model_dir(model)
        dest.mkdir(parents=True, exist_ok=True)
        for rel in self._fetcher.list_repo_files(repo_url):
            if rel in self._HF_SKIP:
                continue
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            self._fetcher.download_file(f"{repo_url}/resolve/main/{rel}", target, progress)

        missing = [rel for rel in model.required_files if not (dest / rel).is_file()]
        if missing:
            raise RuntimeError(f"下载结果缺必需文件: {missing}")

    def _cleanup(self, model: LocalModel) -> None:
        """清理下载中间产物（.tmp / .extract）与校验未通过的不完整模型目录。"""
        for path in self.models_dir.glob(f"{_TMP_PREFIX}{model.model_id}*"):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)
        if not self.is_downloaded(model):
            # 按文件下载中断会留下半成品目录，一并移除以便下次重试
            shutil.rmtree(self.model_dir(model), ignore_errors=True)
