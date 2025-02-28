import json
import random
import re
import streamlit as st
from langchain_openai import ChatOpenAI
from langchain.schema import SystemMessage, HumanMessage, AIMessage
from PIL import Image

# --- ページ・モデル設定 ---
st.set_page_config(page_title="生成AIタロット占いアプリ", page_icon="🔮", layout="centered")

MODEL = "lucas2024/gemma-2-2b-jpn-it:q8_0"
# MODEL = "hf.co/rinna/deepseek-r1-distill-qwen2.5-bakeneko-32b-gguf:latest"
BASE_URL = "http://localhost:11434/v1"
OPENAI_API_KEY = "ollama"
TEMPERATURE = 0.0
SYSTEM_PROMPT = (
    "あなたは、経験豊富で思慮深く、思いやりがあり、優れた直感と霊感に満ち、"
    "よく当たると評判のタロット占い師です。すべて日本語で回答してください。"
)
chat = ChatOpenAI(
    model_name=MODEL,
    openai_api_base=BASE_URL,
    openai_api_key=OPENAI_API_KEY,
    temperature=TEMPERATURE
)

# --- カードデータ読み込み ---
with open("tarot_cards.json", "r", encoding="utf-8") as f:
    tarot_cards_raw = json.load(f)

if isinstance(tarot_cards_raw, dict):
    cards_list = []
    for key, card in tarot_cards_raw.items():
        card["id"] = key
        if "img" not in card:
            card["img"] = f"cards/{key}.jpg"
        cards_list.append(card)
else:
    cards_list = tarot_cards_raw

# --- セッション状態の初期化 ---
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
if "conversation" not in st.session_state:
    st.session_state.conversation = []
if "deck" not in st.session_state:
    st.session_state.deck = list(range(len(cards_list)))
if "reading_done" not in st.session_state:
    st.session_state.reading_done = False

# --- 会話履歴を表示する関数 ---
def display_conversation():
    for msg in st.session_state.conversation:
        if msg["role"] == "user":
            st.chat_message("user").markdown(msg["content"])
        elif msg["role"] == "assistant":
            if msg.get("type") == "card_result":
                result = msg["content"]
                # シグニフィケーターの表示
                if result.get("significator"):
                    sig = result["significator"]
                    try:
                        sig_img = Image.open(sig["img"])
                        st.chat_message("assistant").image(sig_img, caption=f"シグニフィケーター: {sig['name']}", width=150)
                    except Exception as e:
                        st.chat_message("assistant").write(f"シグニフィケーター画像の読み込みに失敗しました: {e}")
                # 10枚のカードの表示
                for card in result.get("cards", []):
                    st.chat_message("assistant").markdown(
                        f"**{card['position']}. {card['name']}（{card['orientation']}）**"
                    )
                    try:
                        img = Image.open(card["img"])
                        if card["orientation"] == "逆位置":
                            img = img.rotate(180)
                        st.chat_message("assistant").image(img, width=150)
                    except Exception as e:
                        st.chat_message("assistant").write(f"カード{card['position']}の画像読み込みに失敗しました: {e}")
                    # 画像の直下にカードの説明を表示
                    if card.get("explanation"):
                        st.chat_message("assistant").markdown(f"説明: {card['explanation']}")
                if result.get("summary"):
                    st.chat_message("assistant").write("**全体の結論:**")
                    st.chat_message("assistant").markdown(result["summary"])
                if result.get("advice"):
                    st.chat_message("assistant").write("**アドバイス:**")
                    st.chat_message("assistant").markdown(result["advice"])
            else:
                st.chat_message("assistant").markdown(msg["content"])

# --- 占いフォーム（初回） ---
if not st.session_state.reading_done:
    st.title("🔮 生成AIタロット占い")
    st.image("images/pkt-gai.jpg", use_container_width=True)
    st.write("アーサー・E・ウェイト『タロット図解』に基づいてケルト十字法で、ライダー社のウェイト=スミス版デッキを用いて、生成AIが占います。")
    st.write("性別と年齢層を選択し、占いたい質問を入力してください。")
    gender = st.selectbox("性別", ["男性", "女性", "その他"])
    age_group = st.selectbox("年齢層", ["40歳未満", "40歳以上"])
    question_text = st.text_area("質問内容", height=100)
    if st.button("この内容で占う"):
        if question_text.strip() == "":
            st.warning("質問内容を入力してください。")
        else:
            user_msg = f"{age_group}の{gender}、質問:\n{question_text}"
            st.session_state.conversation.append({"role": "user", "type": "text", "content": user_msg})
            
            court_cards = [
                card for card in cards_list 
                if any(rank in card.get("name", "") for rank in ["Page", "Knight", "Queen", "King"])
            ]
            if gender == "男性":
                rank = "Knight" if age_group == "40歳以上" else "King"
            elif gender == "女性":
                rank = "Queen" if age_group == "40歳以上" else "Page"
            else:
                rank = random.choice(["Page", "Knight", "Queen", "King"])
            candidates = [card for card in court_cards if card.get("name", "").startswith(rank)]
            significator_name = None
            if candidates:
                sig_card = random.choice(candidates)
                significator_name = sig_card["name"]
                sig_index = cards_list.index(sig_card)
                if sig_index in st.session_state.deck:
                    st.session_state.deck.remove(sig_index)
            
            drawn_cards_indices = random.sample(st.session_state.deck, 10)
            for idx in drawn_cards_indices:
                st.session_state.deck.remove(idx)
            drawn_cards = []
            for i, idx in enumerate(drawn_cards_indices, start=1):
                card = cards_list[idx]
                orientation = "逆位置" if random.choice([True, False]) else "正位置"
                drawn_cards.append({
                    "position": i,
                    "name": card["name"],
                    "orientation": orientation,
                    "img": card["img"]
                })
            
            user_intro = f"{age_group}の{gender}です。"
            user_question = f"質問: {question_text}"
            spread_info = ""
            if significator_name:
                spread_info += f"シグニフィケーターは「{significator_name}」です。\n"
            spread_info += "ケルト十字法の展開結果:\n"
            for card in drawn_cards:
                spread_info += f"{card['position']}. {card['name']}（{card['orientation']}）\n"
            spread_info += "以上のカードが出ました。"
            full_prompt = (
                f"{user_intro}\n{user_question}\n{spread_info}\n"
                "各カードの意味と位置の解釈、そして全体の結論とアドバイスを、改行を適宜入れて読みやすく、"
                "日本語で詳しく教えてください。"
                "回答は厳密に以下のPythonプログラムのフォーマットでお願いします。これ以外のものは表示しないでください"
'''
```python
significator = シグニフィケーターの名前
results = [
  { "name": card[0]['name'], "orientation": card[0]['orientation'], "explanation": card[0]['explanation'] },
  { "name": card[1]['name'], "orientation": card[1]['orientation'], "explanation": card[1]['explanation'] },
  ...
  { "name": card[9]['name'], "orientation": card[9]['orientation'], "explanation": card[9]['explanation'] }
]

conclusion = 結論
advaice = アドバイス```'''
            )
            st.session_state.messages.append({"role": "user", "content": full_prompt})
            response = chat.invoke([
                SystemMessage(content=st.session_state.messages[0]["content"]),
                HumanMessage(content=full_prompt)
            ])
            assistant_text = response.content.strip()
            st.session_state.messages.append({"role": "assistant", "content": assistant_text})
            
            st.write("### LLM の生の回答（デバッグ用）")
            st.code(assistant_text)
            
            code_block_match = re.search(r"```python(.*?)```", assistant_text, re.DOTALL)
            if code_block_match:
                code_text = code_block_match.group(1).strip()
            else:
                code_text = assistant_text

            significator_pattern = r"significator\s*=\s*['\"]([^'\"]+)['\"]"
            significator_match = re.search(significator_pattern, code_text)
            significator_value = significator_match.group(1).strip() if significator_match else None

            results_pattern = r"results\s*=\s*\[(.*?)\]\s*"
            results_match = re.search(results_pattern, code_text, re.DOTALL)
            results_list = []
            if results_match:
                results_text = results_match.group(1)
                card_pattern = r'\{\s*"name":\s*"([^"]+)"(?:\s*\.lower\(\))?\s*,\s*"orientation":\s*"([^"]+)"\s*,\s*"explanation":\s*"([^"]+)"\s*\}'
                cards = re.findall(card_pattern, results_text)
                for card in cards:
                    results_list.append({
                        "name": card[0].strip(),
                        "orientation": card[1].strip(),
                        "explanation": card[2].strip()
                    })

            conclusion_pattern = r"conclusion\s*=\s*\"(.*?)\""
            conclusion_match = re.search(conclusion_pattern, code_text, re.DOTALL)
            conclusion_text = conclusion_match.group(1).strip() if conclusion_match else ""

            advaice_pattern = r"advaice\s*=\s*\"(.*?)\""
            advaice_match = re.search(advaice_pattern, code_text, re.DOTALL)
            advice_text = advaice_match.group(1).strip() if advaice_match else ""

            result_block = {
                "significator": None,
                "cards": [],
                "summary": conclusion_text,
                "advice": advice_text
            }
            if significator_value:
                sig_card_info = next((c for c in cards_list if c["name"] == significator_value), None)
                if sig_card_info:
                    result_block["significator"] = {
                        "name": significator_value,
                        "img": sig_card_info["img"],
                        "orientation": "正位置"
                    }
            for i, card in enumerate(drawn_cards, start=0):
                explanation = results_list[i]["explanation"] if i < len(results_list) else ""
                result_block["cards"].append({
                    "position": card["position"],
                    "name": card["name"],
                    "img": card["img"],
                    "orientation": card["orientation"],
                    "explanation": explanation
                })

            st.session_state.conversation.append({
                "role": "assistant",
                "type": "card_result",
                "content": result_block
            })
            st.session_state.reading_done = True

display_conversation()

if st.session_state.reading_done:
    user_new_message = st.chat_input("追加の質問を入力してください...")
    if user_new_message:
        st.session_state.conversation.append({
            "role": "user",
            "type": "text",
            "content": user_new_message
        })
        draw_extra = False
        new_card = None
        new_orientation = None
        if any(kw in user_new_message for kw in ["もう一枚", "追加で", "カード"]):
            if st.session_state.deck:
                new_idx = random.choice(st.session_state.deck)
                st.session_state.deck.remove(new_idx)
                new_card = cards_list[new_idx]
                new_orientation = "逆位置" if random.choice([True, False]) else "正位置"
                user_new_message += f"\n（※システム: 新たなカード「{new_card['name']}」({new_orientation})を引きました）"
                draw_extra = True
        st.session_state.messages.append({"role": "user", "content": user_new_message})
        lc_messages = []
        for msg in st.session_state.messages:
            if msg["role"] == "system":
                lc_messages.append(SystemMessage(content=msg["content"]))
            elif msg["role"] == "user":
                lc_messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                lc_messages.append(AIMessage(content=msg["content"]))
        response = chat.invoke(lc_messages)
        assistant_reply = response.content.strip()
        st.session_state.messages.append({"role": "assistant", "content": assistant_reply})
        st.session_state.conversation.append({
            "role": "assistant",
            "type": "text",
            "content": assistant_reply
        })
        display_conversation()
