# -*- coding: utf-8 -*-
"""
Streamlit: 古代ケルト十字法タロット占い（A.E.ウェイト『タロット図解』準拠）

- LLM の設定は WSL / macOS × Ollama / LM Studio を引数または環境変数で切替
- 定数は data/tarot_meta.json、カード定義は data/tarot_cards.json
- 入力は Streamlit の form を使用（Enter 送信可）
- 象徴カード（シグニフィケーター）には逆位置はないものとする
- 逆位置は CSS transform: rotate で表現
- 自分自身に関する質問は、象徴カードをコート（宮廷）カードから、TF-IDF類似度で選定
- 自分自身に関することでない質問は、象徴カードを全カードから、TF-IDF類似度で選定
- 各カードの解釈／まとめ／アドバイスを LLM でストリーム生成
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import random
import subprocess
import sys
from datetime import datetime
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple, Union, TypedDict

import streamlit as st
from langchain.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


# ========================= 型定義 =========================

class Card(TypedDict, total=False):
    """カード1枚の定義"""
    index: int                # 0..77
    img_id: str               # 画像ファイル名 "00".."77"
    japanese_name: str        # 日本語名
    name: str                 # 英語名
    looking: str              # 視線の向き "right" | "left" | "unclear"
    symbol: str               # 象徴の説明（英語）
    upright: str              # 正位置の意味（英語）
    reversed: str             # 逆位置の意味（英語）


class DealtCard(TypedDict):
    """スプレッドに配置されたカード"""
    index: int                # スプレッド内の位置（0 は象徴カード）
    img_id: str
    japanese_name: str
    name: str
    orientation: str          # "upright" | "reversed" | "N/A (Significator)"
    symbol: str
    upright: str
    reversed: str


# ========================= ページ設定 =========================

st.set_page_config(
    page_title="生成AIによるタロット占い: 古代ケルト十字法",
    page_icon="🔮",
    layout="centered",
)


# ========================= LLM 設定ユーティリティ =========================

def is_macos() -> bool:
    """実行環境が macOS かどうかを判定する。"""
    return sys.platform == "darwin"


def is_wsl() -> bool:
    """WSL 環境かどうかを判定する（/proc/version を簡易チェック）。"""
    try:
        with open("/proc/version", "r", encoding="utf-8", errors="ignore") as f:
            s = f.read().lower()
        return "microsoft" in s or "wsl" in s
    except Exception:
        return False


def get_windows_host_ip() -> str:
    """
    WSL→Windows のホスト IP を推定する。
    1) /etc/resolv.conf の nameserver
    2) ルートテーブルのデフォルトゲートウェイ
    見つからなければ 127.0.0.1
    """
    try:
        with open("/etc/resolv.conf", "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if line.strip().startswith("nameserver"):
                    ip = line.split()[1]
                    if ip.count(".") == 3:
                        return ip
    except Exception:
        pass
    try:
        out = subprocess.check_output(
            ["sh", "-lc", "ip route show default | awk '{print $3}'"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        if out:
            return out.split()[0]
    except Exception:
        pass
    return "127.0.0.1"


def detect_platform() -> str:
    """実行プラットフォームを識別する。"""
    if is_macos():
        return "macos"
    if is_wsl():
        return "wsl"
    return sys.platform  # "linux", "win32" など


def parse_args() -> argparse.Namespace:
    """
    streamlit 経由で、余計な引数があってもおかしくならないように parse_known_args
    を使用してコマンドライン引数を解釈する。
    """
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--backend", choices=["ollama", "lmstudio"],
                        help="LLM backend (ollama or lmstudio)")
    parser.add_argument("--model", help="Model name (override)")
    parser.add_argument("--base_url", help="Base URL of the OpenAI-compatible API (override)")
    parser.add_argument("--api_key", help="API key (override)")
    parser.add_argument("--temperature", type=float, help="Sampling temperature")
    args, _ = parser.parse_known_args(sys.argv[1:])
    return args


def resolve_llm_config() -> Tuple[str, str, str, float, str, str]:
    """
    LLM 接続設定を行う。
    優先順位: コマンドライン引数 > 環境変数 > デフォルト

    Returns:
        (model, base_url, api_key, temperature, backend, platform)
    """
    args = parse_args()
    backend = (args.backend or os.getenv("LLM_BACKEND", "")).strip().lower() or "ollama"
    platform = detect_platform()

    if backend == "ollama":
        default_model = "gemma3:4b-it-qat"
        default_base = "http://localhost:11434/v1"
        default_key = "ollama"
    else:
        if platform == "macos":
            default_model = "mlx-community/gemma-3-4b-it-qat"
            default_base = "http://localhost:1234/v1"
        elif platform == "wsl":
            default_model = "gemma-3-4b-it-qat"
            default_base = f"http://{get_windows_host_ip()}:1234/v1"
        else:
            default_model = "gemma-3-4b-it-qat"
            default_base = "http://localhost:1234/v1"
        default_key = "lmstudio"

    model = args.model or os.getenv("LLM_MODEL", default_model)
    base_url = args.base_url or os.getenv("LLM_BASE_URL", default_base)
    api_key = args.api_key or os.getenv("OPENAI_API_KEY", default_key)
    temperature = args.temperature if args.temperature is not None else float(
        os.getenv("LLM_TEMPERATURE", "0.9")
    )

    return model, base_url, api_key, temperature, backend, platform


MODEL, BASE_URL, OPENAI_API_KEY, TEMPERATURE, LLM_BACKEND, LLM_PLATFORM = resolve_llm_config()

SYSTEM_PROMPT: str = (
    "あなたは、経験豊富で思慮深く、思いやりがあり、優れた直感と霊感に満ち、よく当たると評判のタロット占い師です。"
    "すべて日本語で回答してください。"
)


# ========================= 外部ファイル読み込み =========================

@st.cache_data(show_spinner=False)
def load_tarot_meta(path: str = "data/tarot_meta.json") -> Dict[str, Any]:
    """
    タロットのメタ情報（ラベル等）を読み込む。

    Args:
        path: JSON ファイルパス

    Returns:
        メタ情報ディクショナリ（読み込めなかった時は空）
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        st.error(f"{path} が見つかりません。")
        return {}
    except Exception as e:
        st.error(f"{path} の読み込みに失敗しました: {e}")
        return {}


_meta: Dict[str, Any] = load_tarot_meta()

# 正位置／逆位置の日本語ラベル
ORIENT_LABEL: Dict[str, str] = _meta.get(
    "orient_label", {"upright": "正位置(upright)", "reversed": "逆位置(reversed)"}
)


def _normalize_item(raw: Union[str, Dict[str, Any]]) -> Optional[Card]:
    """
    JSON の要素（str or dict）を Card 形式に正規化する。

    Returns:
        正規化済み Card / 変換できなかった場合は None
    """
    try:
        item: Dict[str, Any] = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(item, dict):
            return None
        idx = int(item.get("index", 0))
        item["index"] = idx
        item["img_id"] = f"{idx:02d}"
        item.setdefault("japanese_name", "")
        item.setdefault("name", "")
        item.setdefault("looking", "unclear")
        item.setdefault("symbol", "")
        item.setdefault("upright", "")
        item.setdefault("reversed", "")
        return item  # type: ignore[return-value]
    except Exception:
        return None


@st.cache_data(show_spinner=False)
def load_tarot_cards(path: str = "data/tarot_cards.json") -> List[Card]:
    """
    カード定義のリストを JSON から読み込み、index 昇順で返す。
    不正な要素はスキップし、件数を警告表示する。
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        st.error(f"{path} が見つかりません。")
        return []
    except Exception as e:
        st.error(f"{path} の読み込みに失敗しました: {e}")
        return []

    if not isinstance(data, list):
        st.error(f"{path} のルートは配列である必要があります。")
        return []

    normalized: List[Card] = []
    bad = 0
    for el in data:
        norm = _normalize_item(el)
        if norm is None:
            bad += 1
            continue
        normalized.append(norm)

    if bad:
        st.warning(f"JSON（{path}）内に不正な形式の要素が {bad} 件あり、スキップしました。")
    normalized.sort(key=lambda x: x.get("index", 0))  # type: ignore[arg-type]
    return normalized


@st.cache_data(show_spinner=False)
def img_to_base64(path: str) -> str:
    """
    画像ファイルを base64 文字列に変換する。
    ファイルが無い場合は 1px 透明 PNG を返す。
    """
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except FileNotFoundError:
        # 透明1px PNG
        return "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGMAAQAABQABDQottgAAAABJRU5ErkJggg=="


cards_db: List[Card] = load_tarot_cards()


# ========================= ヘッダー =========================

st.title("生成AIによるタロット占い")
st.text("LLMによる古代ケルト十字法タロット占い。")
st.text("ウェイト=スミス版タロットを用い、A.E.ウェイト『タロット図解』に基づいてリーディングします。")
st.image("images/pkt-gai.jpg", width="stretch")


# ========================= 入力（フォーム） =========================

with st.form("reading_form", clear_on_submit=False):
    sex: str = st.selectbox("性別を選択してください。", ["男", "女", "その他"])
    age_category: str = st.radio("年齢を選択してください。", ["40歳未満", "40歳以上"])
    over_40: bool = (age_category == "40歳以上")
    is_self: bool = (st.radio("占いたいのは質問者自身のことですか？", ["はい", "いいえ"]) == "はい")
    query_text: str = st.text_input("占って欲しい内容を入力してください。")
    submitted: bool = st.form_submit_button("占う", type="primary")


# ========================= リセット関数 =========================

def reset_all() -> None:
    """セッション・キャッシュを全消去して rerun する。"""
    try:
        for k in list(st.session_state.keys()):
            del st.session_state[k]
    except Exception:
        pass
    try:
        st.cache_data.clear()
    except Exception:
        pass
    try:
        st.cache_resource.clear()
    except Exception:
        pass
    st.rerun()


# ========================= LLM ユーティリティ =========================

def build_llm() -> ChatOpenAI:
    """
    LangChain の ChatOpenAI を構築する。
    """
    return ChatOpenAI(
        model=MODEL,
        base_url=BASE_URL,
        temperature=TEMPERATURE,
        api_key=OPENAI_API_KEY,
    )


def stream_chat(chat: ChatOpenAI, messages: List[Union[HumanMessage, AIMessage, SystemMessage]],
) -> Iterator[str]:
    """
    ChatOpenAI.stream による逐次出力をジェネレータで返す。
    """
    for chunk in chat.stream(messages):
        if getattr(chunk, "content", None):
            yield chunk.content


def write_stream(text_iter: Iterable[str]) -> str:
    """
    Streamlit に対して、ストリーム表示が可能なら st.write_stream、
    そうでなければ逐次描画する。
    """
    if hasattr(st, "write_stream"):
        return st.write_stream(text_iter)  # type: ignore[call-arg]
    ph = st.empty()
    buf = ""
    for piece in text_iter:
        buf += piece
        ph.markdown(buf)
    return buf


# ========================= ロジック =========================

def translate_query(query: str, chat: ChatOpenAI) -> str:
    """
    日本語の質問を英訳する（英文との類似度計算のため）。
    """
    if not query.strip():
        return ""
    prompt = "次の日本語を英語に訳してください。訳した文章だけを返してください：\n\n" + query
    resp: AIMessage = chat.invoke([HumanMessage(content=prompt)])  # type: ignore[assignment]
    return resp.content.strip()


def is_court_of_rank(card_name: str, rank: str) -> bool:
    """カード英名がコートカードかどうか。"""
    return card_name.startswith(f"{rank} of ")


def get_candidate_cards(self_flag: bool, sex: str, over_40: bool) -> List[Card]:
    """
    象徴カードの候補を返す。
    自分に関する占いなら年齢と性別でコートカードを絞り込む。
    """
    if not self_flag:
        return cards_db

    if sex == "男":
        targets = ["Knight"] if over_40 else ["King"]
    elif sex == "女":
        targets = ["Queen"] if over_40 else ["Page"]
    else:
        targets = ["Knight", "Queen"] if over_40 else ["King", "Page"]

    courts = [c for c in cards_db if any(is_court_of_rank(c.get("name", ""), r) for r in targets)]
    if not courts:
        all_courts = ["King", "Queen", "Knight", "Page"]
        courts = [c for c in cards_db if any(is_court_of_rank(c.get("name", ""), r) for r in all_courts)]
    return courts or cards_db


def choose_card(candidates: List[Card], query_en: str) -> Card:
    if not candidates:
        return {}  # type: ignore[return-value]
    if not query_en.strip():
        return random.choice(candidates)

    corpus = [c.get("symbol", "") for c in candidates] + [query_en]
    vec = TfidfVectorizer().fit(corpus)
    M = vec.transform([c.get("symbol", "") for c in candidates])  # (N, d)
    q = vec.transform([query_en])                                  # (1, d)
    sims = (M @ q.T).toarray().ravel()                             # 形状(N,)
    best_idx = int(sims.argmax())
    return candidates[best_idx]

def generate_spread(sig_img_id: str) -> List[Dict[str, Union[Card, str, int]]]:
    """
    象徴カード以外から 10 枚をランダムに選択し、正位置と逆位置をランダムに決める。
    """
    pool = [c for c in cards_db if c["img_id"] != sig_img_id]
    chosen = random.sample(pool, 10)
    return [
        {"index": i, "card": c, "orientation": random.choice(["upright", "reversed"])}
        for i, c in enumerate(chosen, start=1)
    ]


# ========================= 表示（CSS／LLMストリーム） =========================

def render_layout_css(layout: str) -> None:
    """
    古代ケルト十字法スプレッドの CSS を挿入。
    象徴カードの視線の向きlooking（right/left）に応じて 5 枚目／6 枚目の左右を入替。
    """
    base_css = """
<style>
.celtic-cross-container {
  position: relative; width: 704px; height: 556px;
  margin: 0 auto 10px; border: 1px solid #ccc;
}
.card-position { position: absolute; }
.card-position img {
  width: 70px; height: auto;
  filter: drop-shadow(0 0 3px darkgray);
}
.card-pos0 { top: 41%; left: 33%; }
.card-pos1 { top: 40%; left: 34%; }
.card-pos2 { top: 41%; left: 33.5%; transform: rotate(-90deg); }
.card-pos3 { top: 4%; left: 33%; }
.card-pos4 { top: 76%; left: 33%; }
.card-pos7 { top: 76%; left: 86%; }
.card-pos8 { top: 52%; left: 86%; }
.card-pos9 { top: 28%; left: 86%; }
.card-pos10 { top: 4%; left: 86%; }
"""
    css_right = ".card-pos6 { top: 41%; left: 61%; }\n.card-pos5 { top: 41%; left: 4%; }"
    css_left = ".card-pos5 { top: 41%; left: 61%; }\n.card-pos6 { top: 41%; left: 4%; }"
    st.markdown(base_css + (css_right if layout == "right" else css_left) + "\n</style>", unsafe_allow_html=True)


def reading_stream(
    chat: ChatOpenAI,
    sig: DealtCard,
    query_text: str,
    card: DealtCard,
    pos_label: str
) -> Iterator[str]:
    """
    個別カードのリーディングを LLM ストリームで生成する。
    象徴カード（index=0）のときは向きと意味を出さない。
    """
    is_significator = (card.get("index") == 0)
    selected_meaning = "" if is_significator else card.get(card.get("orientation", "upright"), "")
    orient_text = ORIENT_LABEL.get(card.get("orientation", "upright"), "正位置") if not is_significator else ""
    sig_jp = sig.get("japanese_name", "")
    sig_en = sig.get("name", "")
    card_jp = card.get("japanese_name", "")
    card_en = card.get("name", "")
    symbol_text = card.get("symbol", "")

    prompt = (
        "今回の質問: " + query_text + "\n\n"
        "[現在リーディングしようとしているカードの情報]\n"
        f"カード名: {card_jp}（{card_en}）\n"
        f"位置: {pos_label}\n"
        + (f"向き: {orient_text}\n" if orient_text else "")
        + "カードが象徴するもの:\n"
        + symbol_text + "\n"
        + (f"このカードの{orient_text}でのリーディングにおける意味:\n{selected_meaning}\n" if selected_meaning else "")
        + f"\n今回のスプレッド全体に関する象徴カード(Significator): {sig_jp}({sig_en})\n\n"
        "上記カードの意味と位置を踏まえ、質問内容に対するリーディングを簡潔に短く解説してください。\n"
        "改行を適宜入れ、読みやすい文章にしてください。回答に表題は不要です。\n"
        "回答はすべて日本語でお願いします。\n"
    )
    return stream_chat(chat, [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)])


def conclusion_stream(
    chat: ChatOpenAI,
    sig: DealtCard,
    query_text: str,
    all_cards: List[DealtCard],
    pos_labels_en: List[str]
) -> Iterator[str]:
    """
    スプレッド全体を要約（まとめ）する LLM ストリーム。
    """
    sig_en = sig.get("name", "")
    summary = f"significator = {sig_en}\nquery_text = {query_text}\n\n[スプレッド概要 / Spread]\n"
    for c in all_cards:
        idx = c.get("index", 0)
        jp = c.get("japanese_name", "")
        en = c.get("name", "")
        label = pos_labels_en[idx] if idx < len(pos_labels_en) else f"{idx}th"
        orient_str = ORIENT_LABEL.get(c.get("orientation", "upright"), "upright") if idx != 0 else "N/A (Significator)"
        summary += f"・{label}: {jp}（{en}） / {orient_str}\n"
    summary += "\n上記を踏まえた簡潔な短いまとめを、わかりやすく、ていねいな日本語で提示してください。回答に表題は不要です。"
    return stream_chat(chat, [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=summary)])


def advice_stream(
    chat: ChatOpenAI,
    sig: DealtCard,
    query_text: str,
    all_cards: List[DealtCard],
    conclusion_text: str,
    pos_labels_en: List[str]
) -> Iterator[str]:
    """
    まとめ（conclusion_text）も踏まえた実践的アドバイスを LLM ストリームで生成する。
    """
    sig_en = sig.get("name", "")
    summary = f"significator = {sig_en}\nquery_text = {query_text}\n\n[スプレッド概要 / Spread]\n"
    for c in all_cards:
        idx = c.get("index", 0)
        jp = c.get("japanese_name", "")
        en = c.get("name", "")
        label = pos_labels_en[idx] if idx < len(pos_labels_en) else f"{idx}th"
        orient_str = ORIENT_LABEL.get(c.get("orientation", "upright"), "upright") if idx != 0 else "N/A (Significator)"
        summary += f"・{label}: {jp}（{en}） / {orient_str}\n"

    summary += (
        "\n上記の流れと次のまとめをふまえて、実践的でやさしい日本語のアドバイスを簡潔に短く提示してください。回答に表題は不要です。\n"
        "[まとめ / Summary]\n" + conclusion_text
    )

    return stream_chat(chat, [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=summary)])


# ========================= メイン処理 =========================

if submitted:
    st.divider()
    st.header("選ばれたカードの一覧")

    chat = build_llm()

    card_readings: List[Dict[str, str]] = []
    conclusion_text: str = ""
    advice_text: str = ""

    # 日本語→英語（TF-IDFで類似度を計算するため）
    translated_query: str = translate_query(query_text, chat)

    # 象徴カードの候補取得
    candidates: List[Card] = get_candidate_cards(is_self, sex, over_40)
    if not candidates:
        st.error("カードデータが読み込めていません。JSON データを確認ください。")
        st.stop()

    # シグニフィケーター選定
    sig_card: Card = choose_card(candidates, translated_query)
    sig_img_id: str = sig_card.get("img_id", "00")

    # 10枚引く
    spread: List[Dict[str, Union[Card, str, int]]] = generate_spread(sig_img_id)

    # 位置ラベル
    pos_labels_en: List[str] = [
        "The Significator - Represents the Querant or The Issue",
        "Position 1 - What Covers", "Position 2 – What Crosses", "Position 3 – What Crowns",
        "Position 4 - What is Beneath", "Position 5 – What is Behind", "Position 6 – What is Before",
        "Position 7 - Himself", "Position 8 – His House", "Position 9 – Hopes and Fears",
        "Position 10 - What Will Come",
    ]
    pos_labels_ja: List[str] = [
        "象徴カード", "1枚目 現状", "2枚目 試練", "3枚目 目標", "4枚目 原因",
        "5枚目 過去", "6枚目 未来", "7枚目 本音", "8枚目 周囲", "9枚目 予感", "10枚目 結果",
    ]

    # 画面表示用のカード配列を組立（index=0 が象徴カード）
    all_cards: List[DealtCard] = [{
        "index": 0,
        "img_id": sig_img_id,
        "japanese_name": sig_card.get("japanese_name", ""),
        "name": sig_card.get("name", ""),
        "looking": sig_card.get("looking", "unclear"),
        "orientation": "N/A (Significator)",
        "symbol": sig_card.get("symbol", ""),
        "upright": sig_card.get("upright", ""),
        "reversed": sig_card.get("reversed", ""),
    }] + [{
        "index": int(c["index"]),
        "img_id": str(c["card"]["img_id"]),
        "japanese_name": str(c["card"].get("japanese_name", "")),
        "name": str(c["card"]["name"]),
        "orientation": str(c["orientation"]),
        "symbol": str(c["card"].get("symbol", "")),
        "upright": str(c["card"].get("upright", "")),
        "reversed": str(c["card"].get("reversed", "")),
    } for c in spread]  # type: ignore[index]

    # 向き→CSS 回転
    rotations: List[str] = [
        "rotate(0deg)" if c["index"] == 0 else
        ("rotate(180deg)" if c["orientation"] == "reversed" else "rotate(0deg)")
        for c in all_cards
    ]

    # 画像を base64 化
    b64_images: List[str] = [img_to_base64(f"cards/{c['img_id']}.png") for c in all_cards]

    # 視線の向きを反映
    layout: str = str(all_cards[0].get("looking", "unclear"))
    layout = layout if layout in ["right", "left"] else random.choice(["right", "left"])
    render_layout_css(layout)

    # スプレッドを描画
    board_html: str = "".join(
        '<div class="card-position card-pos{idx}"><img src="data:image/png;base64,{img}" alt="card{idx}" style="transform:{rot};" /></div>'.format(  # noqa: E501
            idx=i, img=b64_images[i], rot=rotations[i]
        )
        for i in range(len(b64_images))
    )
    st.markdown(f'<div class="celtic-cross-container">{board_html}</div>', unsafe_allow_html=True)

    def card_line(c: DealtCard) -> str:
        """カード情報の1行表示（位置ラベル + 名称 + 向き）"""
        idx = c.get("index", 0)
        jp = c.get("japanese_name", "")
        en = c.get("name", "")
        base = f"**{pos_labels_ja[idx]}:** {jp}（{en}）"
        if idx == 0:
            return base
        else:
            orient = ORIENT_LABEL.get(c.get("orientation", "upright"), "upright")
            return base + " / " + orient

    st.markdown("<br>".join([card_line(c) for c in all_cards]), unsafe_allow_html=True)

    # ---------- 各カードのリーディング ----------

    st.divider()
    st.header("各カードのリーディング")
    for c in all_cards:
        idx = c.get("index", 0)
        pos_label = pos_labels_ja[idx] if idx < len(pos_labels_ja) else f"{idx}枚目"
        angle = "rotate(0deg)" if idx == 0 else (
            "rotate(180deg)" if c.get("orientation", "upright") == "reversed" else "rotate(0deg)"
        )
        img_b64 = img_to_base64(f"cards/{c.get('img_id','00')}.png")
        jp = c.get("japanese_name", "")
        en = c.get("name", "")
        sub_title = (
            f"{pos_label}: {jp}（{en}）" if idx == 0
            else f"{pos_label}: {jp}（{en}） / {ORIENT_LABEL.get(c.get('orientation','upright'),'upright')}"
        )
        st.subheader(sub_title)
        st.markdown(
            f'''
            <img src="data:image/png;base64,{img_b64}" alt="{en}"
                 style="width:240px; height:auto; transform:{angle};
                        filter: drop-shadow(0 0 3px darkgray);" />
            ''',
            unsafe_allow_html=True,
        )
        reading_body = write_stream(reading_stream(chat, all_cards[0], query_text, c, pos_label))
        card_readings.append({"index": str(idx), "title": sub_title, "body": reading_body})
        st.divider()

    # ---------- まとめ ----------

    st.header("まとめ")
    conclusion_text = write_stream(
        conclusion_stream(chat, all_cards[0], query_text, all_cards, pos_labels_en)
    )

    # ---------- アドバイス ----------

    st.divider()
    st.header("アドバイス")
    advice_text = write_stream(
        advice_stream(chat, all_cards[0], query_text, all_cards, conclusion_text, pos_labels_en)
    )

    # ---------- リセット ----------

    st.divider()
    st.html('<a href="/" style="display:inline-block; padding: 0.5em 1em; border: 1px solid #ccc; border-radius: 0.3em; text-decoration: none;">もう一度占う</a>')
