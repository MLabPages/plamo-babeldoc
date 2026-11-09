"""翻訳エンジンの一覧。エンジンを足すときは Engine を継承したクラスを ENGINES に加える。

各エンジンは「名前・必要な環境変数・データの扱い（学習に使われるか）・BabelDOC への組み込み方」を持つ。
API キーは環境変数から読み、コードや設定ファイルには書かない。
"""

from __future__ import annotations

from .config import LLAMA_URL, MODELS_DIR
from .envkeys import get_env

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"


class Engine:
    id = ""
    label = ""
    kind = "cloud"          # local（PC内）/ cloud（外部に送る）
    vendor = ""
    env_required: tuple[str, ...] = ()
    env_optional: tuple[str, ...] = ()
    privacy_url = ""
    no_training = True       # 送った内容が学習に使われない前提か

    def display_label(self, settings: dict) -> str:
        return self.label

    def privacy(self, settings: dict) -> str:
        return ""

    def missing_env(self) -> list[str]:
        return [n for n in self.env_required if not get_env(n)]

    def available(self, settings: dict) -> tuple[bool, str]:
        missing = self.missing_env()
        if missing:
            return False, "環境変数 " + "、".join(missing) + " を設定すると使えます。"
        return True, ""

    def info(self, settings: dict) -> dict:
        ok, why = self.available(settings)
        return {
            "id": self.id,
            "label": self.display_label(settings),
            "kind": self.kind,
            "vendor": self.vendor,
            "available": ok,
            "why": why,
            "privacy": self.privacy(settings),
            "no_training": self.no_training,
            "privacy_url": self.privacy_url,
            "env": [{"name": n, "set": bool(get_env(n)), "required": True} for n in self.env_required]
            + [{"name": n, "set": bool(get_env(n)), "required": False} for n in self.env_optional],
        }

    def child_env_names(self) -> list[str]:
        return list(self.env_required + self.env_optional)

    # ---- 翻訳プロセス側（BabelDOC を読み込んだ後に呼ばれる） ----
    def configure(self, bmain, settings: dict, translate_references: bool) -> list[str]:
        raise NotImplementedError


class PlamoEngine(Engine):
    kind = "local"
    vendor = "Preferred Networks（PC内）"
    privacy_url = ""

    def __init__(self, id_: str, label: str, file: str, alias: str):
        self.id, self.label, self.file, self.alias = id_, label, file, alias

    def available(self, settings):
        if not (MODELS_DIR / self.file).exists():
            return False, "モデルファイルがありません。"
        return True, ""

    def privacy(self, settings):
        return "PC内で翻訳します。論文は外部に送られません。"

    def configure(self, bmain, settings, translate_references):
        from .translators import PlamoTranslator, with_reference_policy

        bmain.OpenAITranslator = with_reference_policy(PlamoTranslator, translate_references)
        return ["--openai", "--openai-model", self.alias, "--openai-base-url", f"{LLAMA_URL}/v1",
                "--openai-api-key", "local", "--no-auto-extract-glossary", "--qps", "4", "--pool-max-workers", "4"]


class GeminiEngine(Engine):
    id = "gemini"
    vendor = "Google"
    env_required = ("GEMINI_API_KEY",)
    privacy_url = "https://ai.google.dev/gemini-api/terms"
    no_training = False

    def display_label(self, settings):
        return f"Gemini（{settings.get('gemini_model') or DEFAULT_GEMINI_MODEL}）"

    def privacy(self, settings):
        return ("本文をGoogleのGemini APIへ送ります。課金を有効にした有料枠では、送った内容は製品改善に使われません。"
                "無料枠では使われることがあります。このアプリからはどちらの枠かを判定できません。")

    def configure(self, bmain, settings, translate_references):
        import os

        from .translators import GeminiTranslator, with_reference_policy

        bmain.OpenAITranslator = with_reference_policy(GeminiTranslator, translate_references)
        base_url = os.environ.get("PAPERAPP_GEMINI_BASE_URL", GEMINI_BASE_URL)  # 試験用に差し替え可能
        return ["--openai", "--openai-model", settings.get("gemini_model") or DEFAULT_GEMINI_MODEL,
                "--openai-base-url", base_url, "--openai-api-key", get_env("GEMINI_API_KEY"),
                "--no-auto-extract-glossary", "--qps", "4", "--pool-max-workers", "4"]


class MTEngine(Engine):
    """DeepL / Azure / Google のような翻訳 API。BabelDOC の翻訳部品を差し替える。"""

    translator = ""   # mt_translators 内のクラス名
    qps = "5"

    def configure(self, bmain, settings, translate_references):
        from . import mt_translators
        from .translators import with_reference_policy

        cls = with_reference_policy(getattr(mt_translators, self.translator), translate_references)
        bmain.OpenAITranslator = lambda **kw: cls(kw["lang_in"], kw["lang_out"], kw.get("ignore_cache", False))
        # --openai は BabelDOC の起動条件を満たすためだけの指定（実際の送信先は上の翻訳部品）
        return ["--openai", "--openai-model", self.id, "--openai-api-key", "not-used",
                "--no-auto-extract-glossary", "--qps", self.qps, "--pool-max-workers", "4"]


class DeepLEngine(MTEngine):
    id = "deepl"
    label = "DeepL API（Pro）"
    vendor = "DeepL"
    env_required = ("DEEPL_API_KEY",)
    privacy_url = "https://www.deepl.com/en/privacy"
    translator = "DeepLTranslator"

    def display_label(self, settings):
        if get_env("DEEPL_API_KEY").endswith(":fx"):
            return "DeepL API（Free）"
        return self.label

    def privacy(self, settings):
        if get_env("DEEPL_API_KEY").endswith(":fx"):
            return ("DeepL API Free のキーです。Pro版と同じデータ保護（翻訳後に削除・学習に使わない）が"
                    "適用されるかは、DeepL の契約条件を確認してください。")
        return "有料のDeepL API Pro：本文は翻訳後に削除され、学習には使われません。"


class AzureEngine(MTEngine):
    id = "azure"
    label = "Azure Translator"
    vendor = "Microsoft"
    env_required = ("AZURE_TRANSLATOR_KEY",)
    env_optional = ("AZURE_TRANSLATOR_REGION", "AZURE_TRANSLATOR_ENDPOINT")
    privacy_url = "https://learn.microsoft.com/azure/ai-services/translator/text-translation/overview"
    translator = "AzureTranslator"

    def privacy(self, settings):
        return "Azure Translator：本文は保存されず（No Trace）、学習には使われません。"


class GoogleCloudEngine(MTEngine):
    id = "google"
    label = "Google Cloud Translation"
    vendor = "Google Cloud"
    env_required = ("GOOGLE_CLOUD_TRANSLATE_API_KEY",)
    env_optional = ("GOOGLE_CLOUD_TRANSLATE_ENDPOINT",)
    privacy_url = "https://cloud.google.com/translate/data-usage"
    translator = "GoogleCloudTranslator"

    def privacy(self, settings):
        return "Cloud Translation：本文は翻訳のため一時的に処理されるだけで、学習に使われず第三者にも共有されません。"


ENGINES: dict[str, Engine] = {e.id: e for e in [
    PlamoEngine("plamo-0.8b", "PLaMo 0.8B（最速）", "plamo-3-translate-0.8b-Q4_K_M.gguf", "plamo-3-translate-0.8b"),
    PlamoEngine("plamo-2b", "PLaMo 2B（標準）", "plamo-3-translate-2b-Q4_K_M.gguf", "plamo-3-translate-2b"),
    PlamoEngine("plamo-8b", "PLaMo 8B（高品質・遅め）", "plamo-3-translate-8b-Q4_K_M.gguf", "plamo-3-translate-8b"),
    DeepLEngine(),
    AzureEngine(),
    GoogleCloudEngine(),
    GeminiEngine(),
]}


def engine_list(settings: dict) -> list[dict]:
    return [e.info(settings) for e in ENGINES.values()]


def engine_label(engine_id: str, settings: dict | None = None) -> str:
    e = ENGINES.get(engine_id)
    return e.display_label(settings or {}) if e else engine_id
