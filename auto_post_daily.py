import os
import sys
import json
import base64
import urllib.request
import ssl
import xml.etree.ElementTree as ET

try:
    from google import genai
except ImportError:
    print("必要なライブラリがありません。requirements.txtを確認してください。")
    sys.exit(1)

# --- 設定 ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
WP_APP_PASSWORD = os.environ.get("WP_APP_PASSWORD")
WP_URL = "https://kawacoins.com/index.php?rest_route=/wp/v2/posts"
WP_USER = "@kawacoinclub"

client = genai.Client(api_key=GEMINI_API_KEY)

def get_daily_keywords():
    url = "https://news.google.com/rss/search?q=日本株+NISA+when:1d&hl=ja&gl=JP&ceid=JP:ja"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as res:
            root = ET.fromstring(res.read())
            items = root.findall('.//item')
            return [item.find('title').text.rsplit(" - ", 1)[0] for item in items[:3]]
    except:
        return ["新NISAの活用法", "高配当株トレンド", "日本株の展望"]

def generate_article(keywords):
    kw_text = "\n".join(keywords)
    prompt = f"以下のニュースを元に投資ブログ記事をHTML形式で作成して。1行目は「タイトル: 〇〇」にして。\n{kw_text}"
    try:
        # 最新の呼び出し方式に変更
        response = client.models.generate_content(
            model='gemini-2.0-flash', 
            contents=prompt
        )
        return response.text
    except Exception as e:
        print(f"❌ Geminiエラー: {e}")
        sys.exit(1)

def post_to_wordpress(title, html_content):
    auth = base64.b64encode(f"{WP_USER}:{WP_APP_PASSWORD}".encode()).decode()
    data = json.dumps({"title": title, "content": html_content, "status": "draft"}, ensure_ascii=False).encode()
    req = urllib.request.Request(WP_URL, data=data)
    req.add_header('Content-Type', 'application/json')
    req.add_header('Authorization', f'Basic {auth}')
    ctx = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(req, context=ctx) as res:
            print("✅ WordPress投稿成功！")
    except Exception as e:
        print(f"❌ WP投稿エラー: {e}")

if __name__ == "__main__":
    kw = get_daily_keywords()
    text = generate_article(kw)
    lines = text.strip().split('\n')
    title = lines[0].replace("タイトル:", "").strip()
    content = "\n".join(lines[1:])
    post_to_wordpress(title, content)
