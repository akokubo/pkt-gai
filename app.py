import streamlit as st
import random
import json
from typing import Dict, List, Any, Tuple
from PIL import Image
from langchain_openai import ChatOpenAI
from langchain.schema import SystemMessage, HumanMessage, AIMessage
import base64

# -------------------------------
# 設定値（モデル、API設定、プロンプトなど）
# -------------------------------
MODEL = "lucas2024/gemma-2-2b-jpn-it:q8_0"  # 使用する生成モデル
BASE_URL = "http://localhost:11434/v1"          # API のベース URL
OPENAI_API_KEY = "ollama"                        # API キー
TEMPERATURE = 0.9                                # 生成時のランダム度（温度）
SYSTEM_PROMPT = (
    "あなたは、経験豊富で思慮深く、思いやりがあり、優れた直感と霊感に満ち、よく当たると評判のタロット占い師です。"
    "すべて日本語で回答してください。"
)

# Streamlit ページ全体の設定（レイアウトをワイドに設定）
st.set_page_config(page_title="生成AIによるケルト十字法タロット占い", page_icon="🔮", layout="centered")

# -------------------------------
# タロットカード情報の読み込み
# -------------------------------
# tarot_cards.json からカード情報を読み込み（辞書形式）
with open("tarot_cards.json", "r", encoding="utf-8") as f:
    tarot_cards: Dict[str, Any] = json.load(f)

# -------------------------------
# ユーザー入力（Streamlit UI）
# -------------------------------
st.title("生成AIによるケルト十字法タロット占い")
st.text("アーサー・E・ウェイト『タロット図解』に基づいてケルト十字法で、ライダー社のウェイト=スミス版デッキを用いて、生成AIが占います。")
st.image("images/pkt-gai.jpg", use_container_width=True)

# ユーザーからの属性入力
sex = st.selectbox("性別を選択してください。", ["男", "女", "その他"])
age_category = st.radio("年齢を選択してください。", ["40歳未満", "40歳以上"])
over_40 = (age_category == "40歳以上")
is_self_fortune_requested = (st.radio("占いたいのは質問者自身のことですか？", ["はい", "いいえ"]) == "はい")
# 占ってほしい内容（質問文）の入力
query_text = st.text_input("占って欲しい内容を入力してください。")

# -------------------------------
# 関数定義
# -------------------------------
def translate_query(query: str, chat: ChatOpenAI) -> str:
    """
    入力された日本語の質問文を、LLM を用いて英語に翻訳する。
    プロンプトで「訳した文章だけ」を返すように指示する。
    """
    prompt = f"次の日本語を英語に訳してください。訳した文章だけを返してください：\n\n{query}"
    response: AIMessage = chat.invoke([HumanMessage(content=prompt)])
    return response.content.strip()

def choose_card(cards: List[Tuple[str, Dict[str, Any]]], query: str) -> Tuple[str, Dict[str, Any]]:
    """
    与えられた候補カードリストの中から、質問文（英訳済み）とカード説明文の共通単語数が最も多いカードを選択する。
    """
    query_words = set(query.lower().split())
    best_score, selected_key, selected_card = -1, "", {}
    for key, card in cards:
        score = len(query_words & set(card["description"].lower().split()))
        if score > best_score:
            best_score, selected_key, selected_card = score, key, card
    return selected_key, selected_card

def get_candidate_keys() -> List[str]:
    """
    占う対象に応じて、使用する候補カードのキーのリストを返す。
    自分自身の占いの場合、性別と年齢に応じた候補リストを選択する。
    """
    if not is_self_fortune_requested:
        return list(tarot_cards.keys())
    return (["22", "36", "50", "64"] if sex == "男" and over_40 else
            ["24", "38", "52", "66"] if sex == "男" else
            ["23", "37", "51", "65"] if over_40 else
            ["25", "39", "53", "67"])

def generate_spread(sig_key: str) -> List[Dict[str, Any]]:
    """
    指定されたシグニフィケーター以外のカードからランダムに10枚を選び、
    各カードに正位置か逆位置かをランダムに設定し、スプレッド（配置）を生成する。
    """
    deck = tarot_cards.copy()
    deck.pop(sig_key, None)  # シグニフィケーターは除外
    spread_keys = random.sample(list(deck.keys()), 10)
    spread = [{
        "index": i,
        "key": key,
        "card": deck[key],
        "orientation": random.choice(["正位置", "逆位置"])
    } for i, key in enumerate(spread_keys, start=1)]
    # インデックス順にソートして返す
    return sorted(spread, key=lambda x: x["index"])

def load_and_resize_card(card_info: Dict[str, str]) -> Image.Image:
    """
    指定されたカードの画像を読み込み、逆位置の場合は180度回転、
    その後、50%のサイズにリサイズして返す。
    """
    img = Image.open(f"cards/{card_info['key']}.jpg")
    if card_info["orientation"] == "逆位置":
        img = img.rotate(180)
    w, h = img.size
    return img.resize((w // 2, h // 2))

def generate_reading(chat: ChatOpenAI, selected_card: Dict[str, Any],
                     query_text: str, card_info: Dict[str, Any], pos_label: str) -> str:
    """
    各カードの情報と質問文を基に、LLM によるリーディング（占い結果）を生成する。
    """
    full_prompt = f"""\
significator = {selected_card["name"]}
query_text = {query_text}

[カード情報]
カード名: {card_info["name"]}
位置: {pos_label}
向き: {card_info["orientation"]}
説明文:
{card_info["description"]}

上記のカードの意味と位置を踏まえ、質問内容に対するリーディングを詳しく解説してください。
改行を適宜入れ、読みやすい文章にしてください。
回答に表題は不要です。
回答はすべて日本語でお願いします。
"""
    response: AIMessage = chat.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=full_prompt)
    ])
    return response.content

def generate_conclusion(chat: ChatOpenAI, selected_card: Dict[str, Any],
                        query_text: str, all_cards: List[Dict[str, Any]],
                        position_labels: List[str]) -> str:
    """
    全体のスプレッド情報を元に、LLM によって結論やアドバイスを生成する。
    """
    summary = f"significator = {selected_card['name']}\nquery_text = {query_text}\n\n[スプレッド概要]\n"
    for c in all_cards:
        label = position_labels[c["index"]] if c["index"] < len(position_labels) else f"{c['index']}枚目"
        summary += f"・{label}: {c['name']} ({c['orientation']})\n"
    summary += "\n上記を踏まえた結論とアドバイスを、わかりやすいていねいな日本語でお願いします。"
    response: AIMessage = chat.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=summary)
    ])
    return response.content

# -------------------------------
# メイン処理（ユーザーが「占う」ボタンを押した場合）
# -------------------------------
if st.button("占う"):
    st.divider()
    # ChatOpenAI のインスタンスを生成
    chat = ChatOpenAI(
        model_name=MODEL,
        openai_api_base=BASE_URL,
        openai_api_key=OPENAI_API_KEY,
        temperature=TEMPERATURE
    )

    # ユーザーの質問文を英語に翻訳
    translated_query = translate_query(query_text, chat)
    
    # 占い対象の候補カードキーを取得し、候補カードリストを作成
    candidate_keys = get_candidate_keys()
    candidate_cards = [(key, tarot_cards[key]) for key in candidate_keys]
    # 質問文とカード説明の共通単語数で最も合致するカードを選ぶ（シグニフィケーター）
    sig_key, selected_card = choose_card(candidate_cards, translated_query)
    
    # シグニフィケーター以外のカードからランダムに10枚選び、スプレッドを生成
    spread = generate_spread(sig_key)
    
    # 各カードの位置ラベルを定義
    position_labels = ["シグニフィケーター", "現状", "試練", "目標", "原因", "過去", "未来", "本音", "周囲", "予測", "結果"]

    # シグニフィケーターカードとスプレッドのカードをまとめる
    all_cards = [{
        "index": 0,
        "key": sig_key,
        "name": selected_card["name"],
        "orientation": "正位置",  # シグニフィケーターは常に正位置
        "description": selected_card["description"]
    }] + [{
        "index": card["index"],
        "key": card["key"],
        "name": card["card"]["name"],
        "orientation": card["orientation"],
        "description": card["card"]["description"]
    } for card in spread]

    # 各カードが逆位置の場合、CSS の transform 用の回転値を設定
    rotations = ["rotate(180deg)" if card["orientation"] == "逆位置" else "rotate(0deg)" for card in all_cards]

    # 画像ファイルを Base64 エンコードする関数（HTML に埋め込むため）
    def img_to_base64(path):
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    # 各カード画像を Base64 に変換
    selected_cards_base64 = [img_to_base64(f"cards/{card['key']}.jpg") for card in all_cards]

    # CSS によるケルト十字レイアウトの定義
    st.markdown("""
    <style>
    .celtic-cross-container {position: relative; width: 704px; height: 800px; margin: 0 auto; border: 1px solid #ccc;}
    .card-position {position: absolute;}
    .card-position img {width: 110px; height: auto; border: 1px solid black; filter: drop-shadow(2px 2px 3px gray);}
    .card-pos0 {top: 50.5%; left: 35%; transform: translate(-50%, -50%);}
    .card-pos1 {top: 49.5%; left: 38%; transform: translate(-50%, -50%);}
    .card-pos2 {top: 50%; left: 37%; transform: translate(-50%, -50%) rotate(-90deg);}
    .card-pos3 {top: 24%; left: 37%; transform: translate(-50%, -50%);}
    .card-pos4 {top: 76%; left: 37%; transform: translate(-50%, -50%);}
    .card-pos5 {top: 50%; left: 10%; transform: translate(-50%, -50%);}
    .card-pos6 {top: 50%; left: 64%; transform: translate(-50%, -50%);}
    .card-pos7 {top: 75%; left: 85%; transform: translate(-50%, 0);}
    .card-pos8 {top: 51%; left: 85%; transform: translate(-50%, 0);}
    .card-pos9 {top: 27%; left: 85%; transform: translate(-50%, 0);}
    .card-pos10 {top: 3%; left: 85%; transform: translate(-50%, 0);}
    </style>
    """, unsafe_allow_html=True)

    # 各カードの HTML タグを生成（Base64 画像と回転情報を適用）
    celtic_html = "".join([
        f'<div class="card-position card-pos{i}">'
        f'<img src="data:image/jpeg;base64,{selected_cards_base64[i]}" alt="card{i}" style="transform: {rotations[i]};">'
        f'</div>' for i in range(len(selected_cards_base64))
    ])
    # ケルト十字レイアウトのコンテナに HTML を埋め込み
    st.markdown(f'<div class="celtic-cross-container">{celtic_html}</div>', unsafe_allow_html=True)

    st.divider()
    # 各カードごとのリーディング（占い結果）を生成・表示
    st.header("各カードのリーディング")
    for card in all_cards:
        pos_label = position_labels[card["index"]] if card["index"] < len(position_labels) else f"{card['index']}枚目"
        reading = generate_reading(chat, selected_card, query_text, card, pos_label)
        st.subheader(f"{card['index']}. {pos_label} / {card['name']} ({card['orientation']})")
        st.image(load_and_resize_card(card), caption=f'{card["name"]} ({card["orientation"]})')
        st.write(reading)
        st.divider()

    # 全体の結論・アドバイスを生成し、表示する
    st.header("全体を通しての結論・アドバイス")
    conclusion = generate_conclusion(chat, selected_card, query_text, all_cards, position_labels)
    st.write(conclusion)
