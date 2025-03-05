import streamlit as st
import random
import json
from typing import Dict, List, Any, Tuple
from PIL import Image
from langchain_openai import ChatOpenAI
from langchain.schema import SystemMessage, HumanMessage, AIMessage
import base64
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# =============================================================================
# 基本設定（モデル、API設定、プロンプトなど）
# =============================================================================
MODEL = "lucas2024/gemma-2-2b-jpn-it:q8_0"  # 使用する生成モデル
BASE_URL = "http://localhost:11434/v1"       # API のベース URL
OPENAI_API_KEY = "ollama"                    # API キー
TEMPERATURE = 0.9                            # 生成時のランダム度（温度）
SYSTEM_PROMPT = (
    "あなたは、経験豊富で思慮深く、思いやりがあり、優れた直感と霊感に満ち、よく当たると評判のタロット占い師です。"
    "すべて日本語で回答してください。"
)

# Streamlit のページ設定（タイトル、アイコン、レイアウト）
st.set_page_config(
    page_title="生成AIによるタロット占い: ケルト十字法",
    page_icon="🔮",
    layout="centered"
)

# =============================================================================
# タロットカードデータの読み込み
# =============================================================================
with open("tarot_cards.json", "r", encoding="utf-8") as f:
    tarot_cards: Dict[str, Any] = json.load(f)

# =============================================================================
# ユーザーインターフェース（Streamlit UI）
# =============================================================================
st.title("生成AIによるタロット占い")
st.text("アーサー・E・ウェイト『タロット図解』に基づくケルト十字法で、ライダー版タロットを用いた占いです。")
st.image("images/pkt-gai.jpg", use_container_width=True)

# ユーザー属性と占いたい内容の入力
sex = st.selectbox("性別を選択してください。", ["男", "女", "その他"])
age_category = st.radio("年齢を選択してください。", ["40歳未満", "40歳以上"])
over_40 = (age_category == "40歳以上")
is_self_fortune_requested = (st.radio("占いたいのは質問者自身のことですか？", ["はい", "いいえ"]) == "はい")
query_text = st.text_input("占って欲しい内容を入力してください。")

# =============================================================================
# 補助関数群
# =============================================================================
def translate_query(query: str, chat: ChatOpenAI) -> str:
    """
    質問文を英語に翻訳する関数。
    プロンプト内で「訳した文章のみ」を返すよう指示しています。
    """
    prompt = f"次の日本語を英語に訳してください。訳した文章だけを返してください：\n\n{query}"
    response: AIMessage = chat.invoke([HumanMessage(content=prompt)])
    return response.content.strip()

def choose_card(cards: List[Tuple[str, Dict[str, Any]]], query: str) -> Tuple[str, Dict[str, Any]]:
    """
    候補カードの中から、質問文と各カードの説明文のTF-IDFベクトルを算出し、
    コサイン類似度に基づいて最も類似度が高いカードを選択する関数。
    
    Args:
        cards: (カードキー, カード情報) のリスト
        query: 英語に翻訳された質問文
        
    Returns:
        選ばれたカードのキーとその情報のタプル
    """
    # 全カードの説明文リストを作成
    descriptions = [card["description"] for _, card in cards]
    
    # TF-IDF ベクトル化のため、全説明文と質問文を合わせたコーパスを作成
    corpus = descriptions + [query]
    vectorizer = TfidfVectorizer().fit(corpus)
    
    # 質問文のベクトルを取得
    query_vec = vectorizer.transform([query])
    
    best_score = -1
    selected_key = ""
    selected_card = {}
    
    # 各カードの説明文とのコサイン類似度を計算し、最大のものを選択
    for key, card in cards:
        card_vec = vectorizer.transform([card["description"]])
        score = cosine_similarity(query_vec, card_vec)[0][0]
        if score > best_score:
            best_score = score
            selected_key = key
            selected_card = card
            
    return selected_key, selected_card

def get_candidate_keys() -> List[str]:
    """
    占う対象に応じた候補カードのキーリストを返す関数。
    質問者自身の場合は性別と年齢で候補を絞り込み、それ以外の場合は全カードから選択します。
    """
    if not is_self_fortune_requested:
        return list(tarot_cards.keys())
    # 性別と年齢に基づく候補リスト（例）
    if sex == "男":
        return ["22", "36", "50", "64"] if over_40 else ["24", "38", "52", "66"]
    else:
        return ["23", "37", "51", "65"] if over_40 else ["25", "39", "53", "67"]

def generate_spread(sig_key: str) -> List[Dict[str, Any]]:
    """
    シグニフィケーター以外のカードからランダムに10枚選び、各カードに正位置または逆位置を設定して
    スプレッド（カード配置）を作成する関数。
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
    return sorted(spread, key=lambda x: x["index"])

def load_and_resize_card(card_info: Dict[str, Any]) -> Image.Image:
    """
    カード画像を読み込み、逆位置の場合は180度回転させ、
    その後画像サイズを50%に縮小する関数。
    """
    img = Image.open(f"cards/{card_info['key']}.jpg")
    if card_info["orientation"] == "逆位置":
        img = img.rotate(180)
    w, h = img.size
    return img.resize((w // 2, h // 2))

def generate_reading(chat: ChatOpenAI, selected_card: Dict[str, Any],
                     query_text: str, card_info: Dict[str, Any], pos_label: str) -> str:
    """
    各カードの情報と質問文をもとに、カードごとのリーディング（占い結果）を生成する関数。
    
    Args:
        chat: ChatOpenAI のインスタンス
        selected_card: シグニフィケーターとして選ばれたカード情報
        query_text: ユーザーの質問文（日本語）
        card_info: 対象カードの情報（名前、向き、説明文など）
        pos_label: カードの位置（例：「現状」「未来」など）
        
    Returns:
        生成されたリーディング結果（文字列）
    """
    prompt = f"""\
significator = {selected_card["name"]}
query_text = {query_text}

[カード情報]
カード名: {card_info["name"]}
位置: {pos_label}
向き: {card_info["orientation"]}
説明文:
{card_info["description"]}

上記カードの意味と位置を踏まえ、質問内容に対するリーディングを詳しく解説してください。
改行を適宜入れ、読みやすい文章にしてください。回答に表題は不要です。
回答はすべて日本語でお願いします。
"""
    response: AIMessage = chat.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=prompt)
    ])
    return response.content

def generate_conclusion(chat: ChatOpenAI, selected_card: Dict[str, Any],
                        query_text: str, all_cards: List[Dict[str, Any]],
                        position_labels: List[str]) -> str:
    """
    全カード（シグニフィケーター＋スプレッド）の情報から全体のまとめを生成する関数。
    """
    summary = f"significator = {selected_card['name']}\nquery_text = {query_text}\n\n[スプレッド概要]\n"
    for c in all_cards:
        label = position_labels[c["index"]] if c["index"] < len(position_labels) else f"{c['index']}枚目"
        summary += f"・{label}: {c['name']} ({c['orientation']})\n"
    summary += "\n上記を踏まえたまとめを、わかりやすく、ていねいな日本語でお願いします。回答に表題は不要です。"
    response: AIMessage = chat.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=summary)
    ])
    return response.content

def generate_advice(chat: ChatOpenAI, selected_card: Dict[str, Any],
                    query_text: str, all_cards: List[Dict[str, Any]],
                    conclusion: str, position_labels: List[str]) -> str:
    """
    全カードと先に生成したまとめをもとに、実践的なアドバイスを生成する関数。
    """
    summary = f"significator = {selected_card['name']}\nquery_text = {query_text}\n\n[スプレッド概要]\n"
    for c in all_cards:
        label = position_labels[c["index"]] if c["index"] < len(position_labels) else f"{c['index']}枚目"
        summary += f"・{label}: {c['name']} ({c['orientation']})\n"
    summary += (
        f"\n上記の流れと以下のまとめをふまえて、実践的なアドバイスを、わかりやすく、ていねいな日本語でお願いします。"
        f"回答に表題は不要です。\nまとめ: {conclusion}"
    )
    response: AIMessage = chat.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=summary)
    ])
    return response.content

def img_to_base64(path: str) -> str:
    """
    画像ファイルをBase64エンコードして、HTML埋め込み用の文字列を返す関数。
    """
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def render_layout_css(layout: str) -> None:
    """
    配置レイアウト（"right" または "left"）に応じたCSSスタイルを定義する関数。
    レイアウトによってカードの配置位置が異なります。
    """

    # 共通のCSS
    css1 = """
<style>
.celtic-cross-container {
    position: relative;
    width: 704px;
    height: 556px;
    margin: 0 auto 10px;
    border: 1px solid #ccc;
}
.card-position { position: absolute; }
.card-position img {
    width: 70px;
    height: auto;
    border: 1px solid black;
    border-radius: 3px;
    filter: drop-shadow(0px 0px 3px darkgray);
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

    # シグニフィケーターの見ている方向によって位置が変わるカードのCSS
    if layout == "right":
        css2 = """
.card-pos6 { top: 41%; left: 61%; }
.card-pos5 { top: 41%; left: 4%; }
        """
    else:
        css2 = """
.card-pos5 { top: 41%; left: 61%; }
.card-pos6 { top: 41%; left: 4%; }
        """

    css3 = """
</style>
    """
    st.markdown(css1 + css2 + css3, unsafe_allow_html=True)

# =============================================================================
# メイン処理（ユーザーが「占う」ボタンを押下したとき）
# =============================================================================
if st.button("占う"):
    st.divider()
    st.header("選ばれたカードの一覧")
    
    # ChatOpenAI のインスタンスを生成
    chat = ChatOpenAI(
        model_name=MODEL,
        openai_api_base=BASE_URL,
        openai_api_key=OPENAI_API_KEY,
        temperature=TEMPERATURE
    )

    # ユーザーの質問文を英語に翻訳して、カード選択のための基準とする
    translated_query = translate_query(query_text, chat)
    candidate_keys = get_candidate_keys()
    candidate_cards = [(key, tarot_cards[key]) for key in candidate_keys]
    sig_key, selected_card = choose_card(candidate_cards, translated_query)
    
    # シグニフィケーター以外のカードからランダムに10枚を選び、スプレッドを作成
    spread = generate_spread(sig_key)
    
    # 各カードの配置位置ラベル（シグニフィケーター＋10枚のカード）
    position_labels = ["The Significator – Represents the Querant or The Issue","Position 1 – What Covers", "Position 2 – What Crosses", "Position 3 – What Crowns", "Position 4 – What is Beneath", "Position 5 – What is Behind", "Position 6 – What is Before", "Position 7 – Himself", "Position 8 – His House", "Position 9 – Hopes and Fears", "Position 10 – What Will Come"]
    japanese_position_labels = ["象徴カード", "1枚目 現状", "2枚目 試練", "3枚目 目標", "4枚目 原因", "5枚目 過去", "6枚目 未来", "7枚目 本音", "8枚目 周囲", "9枚目 予感", "10枚目 結果"]

    # シグニフィケーターとスプレッドのカード情報を統合（index, key, name, orientation, description）
    all_cards = [{
        "index": 0,
        "key": sig_key,
        "name": selected_card["name"],
        "looking": selected_card["looking"],
        "orientation": "正位置",  # シグニフィケーターは常に正位置
        "description": selected_card["description"]
    }] + [{
        "index": card["index"],
        "key": card["key"],
        "name": card["card"]["name"],
        "orientation": card["orientation"],
        "description": card["card"]["description"]
    } for card in spread]

    # 各カードが逆位置の場合、CSS 用の回転情報を設定
    rotations = [
        "rotate(180deg)" if card["orientation"] == "逆位置" else "rotate(0deg)"
        for card in all_cards
    ]
    
    # 各カードの画像を Base64 エンコードして HTML 用文字列に変換
    selected_cards_base64 = [img_to_base64(f"cards/{card['key']}.jpg") for card in all_cards]
    
    # レイアウト決定：カードの "looking" 属性が "right" か "left" であればその値を、なければランダムで選択
    layout = all_cards[0]["looking"] if all_cards[0]["looking"] in ["right", "left"] else random.choice(["right", "left"])
    render_layout_css(layout)
    
    # HTML を生成して、各カード画像を配置
    celtic_html = "".join([
        f'<div class="card-position card-pos{i}">'
        f'<img src="data:image/jpeg;base64,{selected_cards_base64[i]}" alt="card{i}" style="transform: {rotations[i]};">'
        f'</div>' for i in range(len(selected_cards_base64))
    ])
    st.markdown(f'<div class="celtic-cross-container">{celtic_html}</div>', unsafe_allow_html=True)
    
    # カードリスト（配置ラベルとカード名、向き）の表示
    card_list = [
        f"**{japanese_position_labels[card['index']]}:** {card['name']} ({card['orientation']})"
        for card in all_cards
    ]
    st.markdown("<br>".join(card_list), unsafe_allow_html=True)
    
    st.divider()
    st.header("各カードのリーディング")
    # 各カードについて、リーディング（占い結果）を生成して表示
    for card in all_cards:
        pos_label = japanese_position_labels[card["index"]] if card["index"] < len(japanese_position_labels) else f"{card['index']}枚目"
        reading = generate_reading(chat, selected_card, query_text, card, pos_label)
        st.subheader(f"{pos_label}: {card['name']} ({card['orientation']})")
        st.image(load_and_resize_card(card), caption=f'{card["name"]} ({card["orientation"]})')
        st.write(reading)
        st.divider()
    
    # 全体のまとめを生成して表示
    st.header("まとめ")
    conclusion = generate_conclusion(chat, selected_card, query_text, all_cards, position_labels)
    st.write(conclusion)
    
    st.divider()
    # まとめと全体スプレッドをもとに、実践的なアドバイスを生成して表示
    st.header("アドバイス")
    advice = generate_advice(chat, selected_card, query_text, all_cards, conclusion, position_labels)
    st.write(advice)
