import os
import sys
import time
from playwright.sync_api import sync_playwright
import requests

# 設定
TARGET_URL = "https://www3.jrhokkaido.co.jp/webunkou/timetable.html?id=088"
LINE_NOTIFY_API = "https://notify-api.line.me/api/notify"
# 環境変数からトークンを取得。ローカルで動かす場合は直接書き換えるか環境変数を設定してください。
LINE_TOKEN = os.getenv("LINE_NOTIFY_TOKEN")

def send_line_notify(message):
    """LINE Notifyでメッセージを送信する"""
    if not LINE_TOKEN:
        print("Error: LINE_NOTIFY_TOKEN is not set.")
        return

    headers = {"Authorization": f"Bearer {LINE_TOKEN}"}
    data = {"message": message}
    try:
        response = requests.post(LINE_NOTIFY_API, headers=headers, data=data)
        response.raise_for_status()
        print("Notification sent successfully.")
    except Exception as e:
        print(f"Failed to send notification: {e}")

def check_train_status():
    """JR北海道の運行情報をチェックする"""
    with sync_playwright() as p:
        # ブラウザ起動 (headless=Trueで画面を表示しない)
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        print(f"Accessing {TARGET_URL}...")
        page.goto(TARGET_URL)
        
        # ページのロード完了を待つ
        page.wait_for_load_state("networkidle")

        try:
            # 「小樽方面」タブをクリック (テキストで探す)
            # 実際のDOM構造に合わせて調整が必要な場合があるが、まずはテキストベースでトライ
            otaru_tab = page.get_by_text("小樽方面")
            if otaru_tab.is_visible():
                otaru_tab.click()
                print("Clicked 'Otaru direction' tab.")
                # タブ切り替え後の描画待ち
                page.wait_for_timeout(2000) 
            else:
                print("Warning: 'Otaru direction' tab not found via text. Layout might have changed.")

            # 遅延・運休情報のチェック
            # HTMLクラス名等はブラウザ調査に基づく推測。実際にはサイトに合わせて調整が必要。
            # .icon-delay (遅延), .icon-unyu (運休), .icon-bubun-unyu (部分運休)
            
            alerts = []
            
            # 遅延
            delays = page.locator(".icon-delay").count()
            if delays > 0:
                alerts.append(f"⚠️ {delays}本の列車で遅延が発生しています。")
                
            # 運休
            cancels = page.locator(".icon-unyu").count()
            if cancels > 0:
                alerts.append(f"❌ {cancels}本の列車が運休しています。")

            # 部分運休
            partial_cancels = page.locator(".icon-bubun-unyu").count()
            if partial_cancels > 0:
                alerts.append(f"⚠️ {partial_cancels}本の列車が部分運休しています。")

            if alerts:
                message = "\n【JR北海道 運行情報】\n発寒中央駅（小樽方面）\n" + "\n".join(alerts)
                print("Alert found! Sending notification...")
                send_line_notify(message)
            else:
                print("No irregularities found. Normal operation assumed.")

        except Exception as e:
            print(f"An error occurred during scraping: {e}")
            # エラー時も通知したい場合はここでsend_line_notifyを呼ぶ
        finally:
            browser.close()

if __name__ == "__main__":
    check_train_status()
