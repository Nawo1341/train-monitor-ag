import os
import sys
import time
import argparse
import requests
import re
from playwright.sync_api import sync_playwright
from datetime import datetime, timedelta, timezone

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
        # ブラウザ起動
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
                page.wait_for_timeout(3000) 
            
            # 日本時間 (JST) を取得
            jst = timezone(timedelta(hours=9))
            now = datetime.now(jst)
            
            start_time = now - timedelta(hours=1)
            end_time = now + timedelta(hours=1)
            
            print(f"--- Debug Info ---")
            print(f"Current JST: {now.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"Checking range: {start_time.strftime('%H:%M')} to {end_time.strftime('%H:%M')}")

            alerts = []
            
            # 時刻表の各行（1時間ごと）をループ
            rows = page.locator("tr").all()
            print(f"Found {len(rows)} table rows.")

            for row in rows:
                # 時を取得 (th.hour)
                hour_elem = row.locator("th.hour")
                if hour_elem.count() == 0:
                    continue
                
                hour_text = hour_elem.inner_text().strip()
                if not hour_text.isdigit():
                    continue
                hour = int(hour_text)
                
                # 時のバリデーション (0-23)
                if not (0 <= hour <= 23):
                    print(f"Skipping invalid hour: {hour}")
                    continue
                
                # その行に含まれる各列車 (div.item) をループ
                items = row.locator("div.item").all()
                for item in items:
                    # 分を取得 (div.min)
                    min_elem = item.locator("div.min")
                    if min_elem.count() == 0:
                        continue
                    
                    min_text = min_elem.inner_text().strip()
                    if not min_text.isdigit():
                        continue
                    minute = int(min_text)
                    
                    # 今日の日付で列車時刻(JST)を作成
                    train_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    
                    # 範囲内かチェック
                    in_range = start_time <= train_time <= end_time
                    
                    # 運行状態の判定 (アイコンがある場合のみ通知対象とする)
                    status = ""
                    img_unkou = item.locator("img.unkou")
                    unkou_code = item.get_attribute("data-unkou")
                    chien_info = item.get_attribute("data-chien")

                    # 1. アイコン(img.unkou)のチェック - これがある場合のみ通知
                    if img_unkou.count() > 0:
                        src = img_unkou.first.get_attribute("src") or ""
                        if "mark_chien" in src:
                            status = "⚠️ 遅延（△）"
                        elif "mark_zenkyu" in src:
                            status = "❌ 運休（✖）"
                        elif "mark_bubunkyu" in src:
                            status = "⚠️ 部分運休（✖）"
                    
                    # 2. データ属性 (参考ログとしてのみ使用し、通知判定には使わない)
                    # ユーザーから「記号がないものは通知不要」との要望があったため
                    
                    # 判定ログを出力
                    if in_range:
                        log_status = status if status else f"Normal (unkou:{unkou_code}, chien:{chien_info})"
                        print(f"  [IN RANGE] {hour:02}:{minute:02} | Status: {log_status}")

                    if in_range and status:
                        alerts.append(f"{hour:02}:{minute:02} 発 - {status}")

            print(f"------------------")

            if alerts:
                unique_alerts = sorted(list(set(alerts)))
                exec_mode = "【定期監視】" if "GITHUB_ACTIONS" in os.environ else "【ローカル実行】"
                
                message = f"\n{exec_mode} JR北海道 運行情報\n発寒中央駅（小樽方面）\n対象時間: {start_time.strftime('%H:%M')}〜{end_time.strftime('%H:%M')}\n\n" + "\n".join(unique_alerts)
                print("Irregularities found! Sending to Discord...")
                send_discord_notify(message)
            else:
                print("No irregularities found in the specified range.")

        except Exception as e:
            print(f"An error occurred during scraping: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="JR Train Monitor")
    parser.add_argument("--test", action="store_true", help="Send a test Discord notification and exit")
    args = parser.parse_args()

    if args.test:
        print("Sending test notification...")
        send_discord_notify("\nDiscord通知テスト: これはテストメッセージです。\nこの通知が届けば連携は成功しています。")
    else:
        check_train_status()
