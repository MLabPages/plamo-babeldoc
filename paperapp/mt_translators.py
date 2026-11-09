"""DeepL / Azure Translator / Google Cloud Translation 用の翻訳部品。

BabelDOC が段落中の太字・数式に付ける目印を、最初から「訳さない」印つきの HTML タグにして、
各 API の HTML 翻訳モードで崩れないようにする。API キーは環境変数から読む。
"""

from __future__ import annotations

import html
import json
import re
import time
import urllib.error
import urllib.request

from . import bdenv  # noqa: F401
from babeldoc.translator.translator import BaseTranslator

from .envkeys import get_env
from .translators import counted

_OUR_TAGS = re.compile(r'(<span translate="no" class="notranslate" id="f\d+">#\d+</span>|<b id="r\d+">|</b>)')


class ApiError(RuntimeError):
    pass


def encode_html(text: str) -> str:
    parts = _OUR_TAGS.split(text)
    return "".join(p if i % 2 else html.escape(p, quote=False) for i, p in enumerate(parts))


def post_json(url: str, body, headers: dict, timeout: float = 60):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    last = ""
    for attempt in range(6):
        req = urllib.request.Request(url, data=data, method="POST",
                                     headers={"Content-Type": "application/json; charset=utf-8", **headers})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            last = f"HTTP {e.code}: {detail}"
            if e.code in (429, 500, 502, 503, 504, 529):
                time.sleep(min(30, 2 ** attempt))
                continue
            raise ApiError(last) from None
        except urllib.error.URLError as e:
            last = f"Connection error: {e.reason}"
            time.sleep(min(10, 2 ** attempt))
    raise ApiError(last)


class HtmlMTTranslator(BaseTranslator):
    name = "html-mt"
    lang_map: dict = {}

    def __init__(self, lang_in, lang_out, ignore_cache=False):
        super().__init__(lang_in, lang_out, ignore_cache)
        self.add_cache_impact_parameters("html_codec", "v1")
        # BabelDOC が終了時に読むトークン数の欄（翻訳 API では使わないので 0 のまま）
        from babeldoc.translator.translator import AtomicInteger

        self.token_count = AtomicInteger()
        self.prompt_token_count = AtomicInteger()
        self.completion_token_count = AtomicInteger()
        self.cache_hit_prompt_token_count = AtomicInteger()

    # BabelDOC の目印を HTML の「訳さない」タグにする（タプルは 目印, 訳文から探す正規表現）
    def get_formular_placeholder(self, pid):
        return (f'<span translate="no" class="notranslate" id="f{pid}">#{pid}</span>',
                rf'<span[^>]*?id\s*=\s*["\']?f{pid}["\']?[^>]*>.*?</span>')

    def get_rich_text_left_placeholder(self, pid):
        return (f'<b id="r{pid}">', rf'<b[^>]*?id\s*=\s*["\']?r{pid}["\']?[^>]*>')

    def get_rich_text_right_placeholder(self, pid):
        return ("</b>", r"<\s*/\s*b\s*>")

    @counted
    def do_translate(self, text, rate_limit_params=None):
        if not text.strip():
            return text
        out = self.call_api(encode_html(text))
        return html.unescape(out)

    def call_api(self, html_text: str) -> str:
        raise NotImplementedError

    def do_llm_translate(self, text, rate_limit_params=None):
        raise NotImplementedError


class DeepLTranslator(HtmlMTTranslator):
    name = "deepl"

    def __init__(self, lang_in, lang_out, ignore_cache=False):
        super().__init__(lang_in, lang_out, ignore_cache)
        self.key = get_env("DEEPL_API_KEY")
        if not self.key:
            raise ApiError("環境変数 DEEPL_API_KEY が設定されていません。")
        self.url = get_env("DEEPL_API_URL") or (
            "https://api-free.deepl.com/v2/translate" if self.key.endswith(":fx")
            else "https://api.deepl.com/v2/translate")

    def call_api(self, html_text: str) -> str:
        body = {"text": [html_text], "source_lang": self.lang_in.upper()[:2], "target_lang": self.lang_out.upper(),
                "tag_handling": "html", "formality": "prefer_less"}
        data = post_json(self.url, body, {"Authorization": f"DeepL-Auth-Key {self.key}"})
        return data["translations"][0]["text"]


class AzureTranslator(HtmlMTTranslator):
    name = "azure"

    def __init__(self, lang_in, lang_out, ignore_cache=False):
        super().__init__(lang_in, lang_out, ignore_cache)
        self.key = get_env("AZURE_TRANSLATOR_KEY")
        if not self.key:
            raise ApiError("環境変数 AZURE_TRANSLATOR_KEY が設定されていません。")
        self.region = get_env("AZURE_TRANSLATOR_REGION")
        endpoint = (get_env("AZURE_TRANSLATOR_ENDPOINT") or "https://api.cognitive.microsofttranslator.com").rstrip("/")
        if "cognitiveservices.azure.com" in endpoint and "/translator/" not in endpoint:
            endpoint += "/translator/text/v3.0"
        self.url = f"{endpoint}/translate?api-version=3.0&from={self.lang_in}&to={self.lang_out}&textType=html"

    def call_api(self, html_text: str) -> str:
        headers = {"Ocp-Apim-Subscription-Key": self.key}
        if self.region:
            headers["Ocp-Apim-Subscription-Region"] = self.region
        data = post_json(self.url, [{"Text": html_text}], headers)
        return data[0]["translations"][0]["text"]


class GoogleCloudTranslator(HtmlMTTranslator):
    name = "google-cloud"

    def __init__(self, lang_in, lang_out, ignore_cache=False):
        super().__init__(lang_in, lang_out, ignore_cache)
        self.key = get_env("GOOGLE_CLOUD_TRANSLATE_API_KEY")
        if not self.key:
            raise ApiError("環境変数 GOOGLE_CLOUD_TRANSLATE_API_KEY が設定されていません。")
        self.url = get_env("GOOGLE_CLOUD_TRANSLATE_ENDPOINT") or "https://translation.googleapis.com/language/translate/v2"

    def call_api(self, html_text: str) -> str:
        body = {"q": [html_text], "source": self.lang_in, "target": self.lang_out, "format": "html"}
        data = post_json(self.url, body, {"X-Goog-Api-Key": self.key})
        return data["data"]["translations"][0]["translatedText"]
