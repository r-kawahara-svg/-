import os
import sys
import json
import base64
import urllib.request
import ssl
import xml.etree.ElementTree as ET

try:
    import requests
    import google.generativeai as genai
except ImportError:
    print("必要なライブラリがインストールされていません。'pip install -r requirements.txt' を実行してください。")
    sys.exit(1)

# ==========================================
# 1. 認証情報の読み込み (GitHub ActionsのSecrets等から)
# ==========================================
# 環境変数から取得（GitHub Actionsで実行されることを前提としています）
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
WP_APP_PASSWORD = os.environ.get("WP_APP_PASSWORD")

# ローカルで直接実行してテストする場合は、以下の変数に直接代入しても動きます
if not GEMINI_API_KEY:
    GEMINI_API_KEY = "ここにGeminiのAPIキーを入力してください"
if not WP_APP_PASSWORD:
    WP_APP_PASSWORD = "ここにWordPressのアプリケーションパスワードを入力してください"

WP_URL = "https://kawacoins.com/index.php?rest_route=/wp/v2/posts"
WP_USER = "@kawacoinclub"

if GEMINI_API_KEY.startswith("ここに"):
    print("エラー: GEMINI_API_KEY が設定されていません。")
    sys.exit(1)

genai.configure(api_key=GEMINI_API_KEY)


# ==========================================
# 関数定義
# ==========================================
def get_daily_keywords():
    """
    GoogleニュースRSSから「日本株 NISA」関連で過去1日以内の最新ニュースを取得し、
    トップ3のキーワード（ニュースタイトル）を返す
    """
    url = "https://news.google.com/rss/search?q=日本株+NISA+when:1d&hl=ja&gl=JP&ceid=JP:ja"
    print(f"📡 ニュースを取得中... ({url})")
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        # XMLをパースして記事を取り出す
        root = ET.fromstring(response.text)
        items = root.findall('.//item')
        
        keywords = []
        for item in items[:3]:  # 上位3件のみ
            title = item.find('title').text
            if title:
                # ニュースサイト名を削る工夫 (" - Yahoo!ニュース"などを削除)
                clean_title = title.rsplit(" - ", 1)[0]
                keywords.append(clean_title)
                
        if not keywords:
            # 取得失敗時のフォールバック
            return ["高配当株の最新トレンド", "新NISAの成長投資枠活用法", "日銀の金融政策と金利動向"]
            
        return keywords
    except Exception as e:
        print(f"❌ ニュース取得エラー: {e}")
        return ["高配当株の最新トレンド", "新NISAの成長投資枠活用法", "日銀の金融政策と金利動向"]

def generate_article(keywords):
    """
    Gemini APIを使って、取得したニュースから2000文字程度のHTML記事を執筆させる
    """
    kw_text = "\n".join([f"・{kw}" for kw in keywords])
    print("\n🧠 以下の最新ニュースを元に Gemini に記事を執筆させています...")
    print(kw_text)
    print("執筆中（約10〜30秒かかります）...")
    
    prompt = f"""
あなたは投資初心者〜中級者向けの人気ブログ「Smart 株Checker」の専属ライターです。
以下の【本日の最新キーワード・ニュース】をもとに、今日の「日本株・新NISA」に関するトレンドを解説するブログ記事の下書きを作成してください。

【本日の最新キーワード・ニュース】
{kw_text}

【記事の必須要件・トーン】
1. 文字数：約2,000文字程度で、読者が満足できる充実した内容にしてください。
2. 文体：読者に親しみやすく語りかけるような「です・ます調」。専門用語は優しく解説してください。
3. 構成：
   - 記事タイトル（<h1>タグは使わず、最初の行に「タイトル: 〇〇」とテキストで出力）
   - リード文（挨拶と本日の相場サマリー）
   - 見出し（<h2> や <h3>タグを適切に使用）
   - 必ず「箇条書き（<ul> または <ol>）」を含めること
   - トレンド要素や注目セクター（業種）を整理した「比較表」（HTMLの <table>タグ）を必ず1つ以上含めること。
   - まとめ（<h2>まとめ</h2>）
4. 画像の挿入プレースホルダ：
   本文内の「ここで図解や関連画像が入ると良い」という箇所（見出しの下など2〜3箇所）に、必ず以下の形式のプレースホルダテキストを挿入してください。
   `[ここに〇〇（具体的な画像内容、例：株価上昇のグラフ）の画像を入れる]`
5. 出力形式：
   途中の会話や「承知しました」などの返事は一切不要です。
   <article>タグやMarkdownのコードブロック(```html)等で囲まないで、純粋なHTML本文のみを直接出力してください。
   （※最初の1行目だけはHTML外で「タイトル: ○○」というプレーンテキストにしてください）
"""
    
    try:
        # 最新のGeminiモデルを指定
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"❌ Gemini記事生成エラー: {e}")
        sys.exit(1)

def post_to_wordpress(title, html_content):
    """
    WordPress REST API経由で記事を「下書き」として投稿する
    """
    print(f"\n📝 WordPressへ下書き投稿を開始します")
    print(f"タイトル: {title}")
    
    auth_str = f"{WP_USER}:{WP_APP_PASSWORD}"
    b64_auth_str = base64.b64encode(auth_str.encode('ascii')).decode('ascii')
    
    post_data = {
        "title": title,
        "content": html_content,
        "status": "draft"
    }
    
    # ensure_ascii=False で文字化け防止
    json_payload = json.dumps(post_data, ensure_ascii=False).encode('utf-8')

    req = urllib.request.Request(WP_URL, data=json_payload)
    req.add_header('Content-Type', 'application/json; charset=utf-8')
    req.add_header('Authorization', f'Basic {b64_auth_str}')
    
    # サーバーのWAFに弾かれないようブラウザ標準のUser-Agentに変更
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    req.add_header('User-Agent', USER_AGENT)
    req.add_header('Accept', 'application/json, */*')

    # SSL証明書エラー回避
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        with urllib.request.urlopen(req, context=ctx) as response:
            result = json.loads(response.read().decode('utf-8'))
            print("✅ SUCCESS: 下書き投稿が完了しました！")
            print("Link:", result.get('link'))
            print("ID:", result.get('id'))
    except urllib.error.HTTPError as e:
        print(f"❌ HTTP ERROR: {e.code}")
        err_body = e.read().decode('utf-8')
        print(err_body[:300] + ("..." if len(err_body) > 300 else ""))
    except Exception as e:
        print(f"❌ ERROR: {e}")


# ==========================================
# メイン処理
# ==========================================
if __name__ == "__main__":
    print("==================================================")
    print("🚀 [Daily Auto Post] ニュース取得〜AI執筆〜WP投稿")
    print("==================================================")
    
    # 1. Googleニュースから今日のキーワードを3つ取得
    keywords = get_daily_keywords()
    
    # 2. Geminiで記事生成
    generated_text = generate_article(keywords)
    
    if not generated_text:
        print("記事が生成されませんでした。処理を終了します。")
        sys.exit(1)
        
    # 3. タイトルと本文の分離
    lines = generated_text.strip().split('\n')
    title = "【AI自動生成】本日の日本株・新NISAニュースまとめ"
    content_lines = []
    
    for line in lines:
        if line.startswith("タイトル:") or line.startswith("タイトル："):
            # タイトル行を抽出して除去
            title = line.replace("タイトル:", "").replace("タイトル：", "").replace("**", "").replace("#", "").strip()
        elif "```html" in line or "```" in line:
            # Markdownコードブロック記号が混入した場合は読み飛ばす
            continue
        else:
            content_lines.append(line)
            
    html_content = "\n".join(content_lines)
    
    # 4. WordPressへ自動投稿
    post_to_wordpress(title, html_content)
    print("==================================================")
    print("🎉 全ての処理が完了しました！")
