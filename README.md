# 生成AIタロット占いアプリ
アーサー・E・ウェイト（Arthur Edward Waite）の『タロット図解（The Pictorial Key to the Tarot）』に基づいて古代ケルト十字法（An Ancient Celtic Method of Divination）で、ライダー社のウェイト=スミス版デッキを用いて、生成AIが占います。

* 小久保 温、「ウェイト＝スミス版タロットに基づいた生成AI占いアプリの開発」、日本デジタルゲーム学会 2025年夏季研究発表大会予稿集、pp. 213-216、2025年9月12日、[https://doi.org/10.57518/digrajprocsummer.2025.0_213](https://doi.org/10.57518/digrajprocsummer.2025.0_213)

<img src="images/pkt-gai.jpg" width="100%" alt="生成AIタロット占いアプリ">


## 使用したもの
* [Streamlit](https://streamlit.io/)
* [LangChain](https://www.langchain.com/)
* [LM Studio](https://lmstudio.ai/)か[Ollama](https://ollama.com/)
* Arthur Edward Waite, Pamela Colman Smith, ["The Pictorial Key to the Tarot"](https://en.wikisource.org/wiki/The_Pictorial_Key_to_the_Tarot), 	William Rider & Son, 1910
* カードの画像, [Rider–Waite Tarot](https://en.wikipedia.org/wiki/Rider%E2%80%93Waite_Tarot)

## インストール
```
git clone https://github.com/akokubo/pkt-gai.git
cd pkt-grai
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install numpy pandas openpyxl scikit-learn streamlit langchain langchain-openai watchdog
```
※Windowsの場合、WSL2の[新しいもの](https://github.com/microsoft/WSL/releases/)をインストールし、`sudo apt update`と`sudo apt upgrade`し、`sudo apt install python3-pip`や`sudo apt install python3-venv`などしてからご利用ください。

### LM Studioの場合
LM StudioかOllamaをインストールする。
1. LM Studioをインストール
  - [LM Studio](https://lmstudio.ai/)から、ダウンロードしてインストール
2. LM Studioで大規模言語モデルの `gemma3:4b-it-qat` などをダウンロードする。
  - 左のアイコンの「探索」で、WSLの場合は`lmstudio-community/gemma-3-4B-it-qat-GGUF`、macOSの場合`mlx-community/gemma-3-4b-it-qat-4bit`をダウンロードする。
3. LM Studioで大規模言語モデルを実行する
  - 左のアイコンの「開発者」で、「モデルを選択してください」で`Gemma 3 4B Instruct QAT`などを選ぶ
  - 「Status」を「Stopped」から「Runningに切り替える
  - 「Server Settings」で「ローカルネットワークで提供」を有効にする

### Ollamaの場合
LM StudioかOllamaをインストールする。

1. Ollamaをインストール
   - Windowsの場合は、WSL2で仮想環境から `curl -fsSL https://ollama.com/install.sh | sh` でインストール
   - Macの場合は、[ダウンロード](https://ollama.com/download/windows)してインストール
2. Ollamaで大規模言語モデルの `gemma3:4b-it-qat` などをpullする。
```
ollama pull gemma3:4b-it-qat
```
3. Ollamaで大規模言語モデルを実行する
Ollamaが実行されていないかもしれないので、大規模言語モデルのリストを表示してみる（表示すると実行される）
```
ollama list
```

## 実行
最初に、プログラムを展開したフォルダに入る。
次に仮想環境に入っていない場合(コマンドプロンプトに(venv)と表示されていないとき)、仮想環境に入る。
```
source .venv/bin/activate
```

仮想環境に入っている状態で、以下のコマンドでアプリを起動する。
```
python3 -m streamlit run app.py
```

<img src="images/pkt-spread.jpg" width="100%" alt="生成AIタロット占いアプリ">

## 作者
[小久保 温(こくぼ・あつし)](https://akokubo.github.io/)

## ライセンス
[MIT License](LICENSE)
