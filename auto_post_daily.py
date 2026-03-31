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
# 1. 認証情報の読み込み
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
WP_APP_PASSWORD = os.environ.get("WP_APP_PASSWORD")

# WordPress設定
WP_URL = "https://kawacoins.com/index.php?rest_route=/wp/v2/posts"
WP_USER = "@kawacoinclub"

if not GEMINI_API_KEY or GEMINI_API_KEY == "ここにGeminiのAPIキーを入力してください":
    print("エラー: GEMINI_API_KEY が正しく設定されていません。")
    sys.exit(1)

genai.configure(api_key=GEMINI_API_KEY)

# ==========================================
# 関数定義
# ==========================================
def get_daily_keywords():
    url = "https://news.google.com/rss/search?q=日本株+NISA+when:1d&hl=ja&gl=JP&ceid=JP:ja"
    print(f"📡 ニュースを取得中... ({url})")
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        root = ET.fromstring(response.text)
        items = root.findall('.//item')
        keywords = []
        for item in items[:3]:
            title = item.find('title').text
            if title:
                clean_title = title.rsplit(" - ", 1)[0]
                keywords.append(clean_title)
        return keywords if keywords else ["高配当株の最新トレンド", "新NISAの成長投資枠活用法", "日銀の政策金利"]
    except Exception as e:
        print(f"❌ ニュース取得エラー: {e}")
        return ["高配当株の最新トレンド", "新NISAの成長投資枠活用法", "日銀の政策金利"]

def generate_article(keywords):
    kw_text = "\n".join([f"・{kw}" for kw in keywords])
    print("\n🧠 Geminiが執筆中（約10〜30秒）...")
    
    prompt = f"""
あなたは投資ブログ「Smart 株Checker」の専属ライターです。
以下のキーワードをもとに、日本株・新NISAのトレンド解説記事をHTML形式で作成してください。
【キーワード】
{kw_text}
【要件】
1. 約2,000文字程度
2. タイトルを1行目に「タイトル: 〇〇」と記載
3. <h2> <h3> <ul> <table> タグを使用
4. 画像プレースホルダ [ここに〇〇の画像を入れる] を3箇所挿入
5. 純粋なHTMLのみを出力
"""
    try:
        # 【修正箇所】モデル名を latest に変更
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"❌ Gemini記事生成エラー: {e}")
        sys.exit(1)

def post_to_wordpress(title, html_content):
    print(f"\n📝 WordPressへ投稿中: {title}")
    auth_str = f"{WP_USER}:{WP_APP_PASSWORD}"
    b64_auth_str = base64.b64encode(auth_str.encode('ascii')).decode('ascii')
    post_data = {"title": title, "content": html_content, "status": "draft"}
    json_payload = json.dumps(post_data, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(WP_URL, data=json_payload)
    req.add_header('Content-Type', 'application/json; charset=utf-8')
    req.add_header('Authorization', f'Basic {b64_auth_str}')
    req.add_header('User-Agent', 'Mozilla/5.0')
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(req, context=ctx) as response:
            result = json.loads(response.read().decode('utf-8'))
            print(f"✅ 成功！投稿URL: {result.get('link')}")
    except Exception as e:
        print(f"❌ 投稿エラー: {e}")

# ==========================================
# メイン処理
# ==========================================
if __name__ == "__main__":
    print("🚀 実行開始")
    keywords = get_daily_keywords()
    generated_text = generate_article(keywords)
    if not generated_text:
        sys.exit(1)
    
    lines = generated_text.strip().split('\n')
    title = "【AI自動生成】本日の投資ニュースまとめ"
    content_lines = []
    for line in lines:
        if line.startswith("タイトル:") or line.startswith("タイトル："):
            title = line.replace("タイトル:", "").replace("タイトル：", "").replace("**", "").replace("#", "").strip()
        elif "```" in line:
            continue
        else:
            content_lines.append(line)
    
    post_to_wordpress(title, "\n".join(content_lines))
    print("🎉 完了しました！")
