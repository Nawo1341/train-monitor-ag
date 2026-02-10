import os
import sys
import time
import argparse
from playwright.sync_api import sync_playwright
import requests

from datetime import datetime, timedelta

# 設定
TARGET_URL = "https://www3.jrhokkaido.co.jp/webunkou/timetable.html?id=088"
# 環境変数からDiscord Webhook URLを取得。
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

def send_discord_notify(message):
    """Discord Webhookでメッセージを送信する"""
    if not DISCORD_WEBHOOK_URL:
        print("Error: DISCORD_WEBHOOK_URL is not set.")
        return

    data = {"content": message}
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=data)
        response.raise_for_status()
        print("Notification sent successfully.")
    except Exception as e:
        print(f"Failed to send notification: {e}")

def check_train_status():
    """JR北海道の運行情報をチェックする"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        print(f"Accessing {TARGET_URL}...")
        page.goto(TARGET_URL)
        page.wait_for_load_state("networkidle")

        try:
            # 「小樽方面」タブをクリック
            otaru_tab = page.get_by_text("小樽方面")
            if otaru_tab.count() > 0:
                otaru_tab.first.click()
                print("Clicked 'Otaru direction' tab.")
                page.wait_for_timeout(2000) 
            
            # 現在時刻の前後1時間の範囲を設定
            now = datetime.now()
            # GitHub ActionsはUTCなので日本時間に合わせる（+9時間）
            # ただしローカル実行も考慮し、実行環境の時刻を基準にする（必要に応じて調整）
            start_time = now - timedelta(hours=1)
            end_time = now + timedelta(hours=1)
            
            print(f"Checking trains between {start_time.strftime('%H:%M')} and {end_time.strftime('%H:%M')}")

            # 列車リストの行を取得 (CSSセレクタはサイト構造に依存)
            # 時刻表の各行をループ
            rows = page.locator("tr").all()
            alerts = []

            for row in rows:
                content = row.inner_text()
                # 「12:34」のような時刻形式を探す
                import re
                time_match = re.search(r"(\d{1,2}):(\d{2})", content)
                if time_match:
                    hour, minute = map(int, time_match.groups())
                    # 昨日の23時台や明日の0時台を考慮せず、今日の時刻として扱う簡略化
                    train_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    
                    # 範囲内かチェック
                    if start_time <= train_time <= end_time:
                        # この行に遅延や運休のアイコンがあるかチェック
                        delay_icon = row.locator(".icon-delay")
                        unyu_icon = row.locator(".icon-unyu")
                        bubun_icon = row.locator(".icon-bubun-unyu")

                        if delay_icon.count() > 0:
                            alerts.append(f"⚠️ {hour:02}:{minute:02} 発 - 遅延が発生しています。")
                        if unyu_icon.count() > 0:
                            alerts.append(f"❌ {hour:02}:{minute:02} 発 - 運休しています。")
                        if bubun_icon.count() > 0:
                            alerts.append(f"⚠️ {hour:02}:{minute:02} 発 - 部分運休しています。")

            if alerts:
                # 重複削除
                unique_alerts = sorted(list(set(alerts)))
                exec_mode = "【手動起動】" if "GITHUB_ACTIONS" in os.environ else "【ローカル実行】"
                
                message = f"\n{exec_mode} JR北海道 運行情報\n発寒中央駅（小樽方面）\n現在時刻の前後1時間の情報:\n" + "\n".join(unique_alerts)
                print("Irregularities found within time range! Sending notification...")
                send_discord_notify(message)
            else:
                print("No irregularities found for the specified time range.")

        except Exception as e:
            print(f"An error occurred during scraping: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="JR Train Monitor")
    parser.add_argument("--test", action="store_true", help="Send a test Discord notification and exit")
    args = parser.parse_args()

    if args.test:
        print("Sending test notification...")
        send_discord_notify("\nDiscord通知テスト: これはテストメッセージです。\nこの通知が届けば連携は成功しています。")
    else:
        check_train_status()
