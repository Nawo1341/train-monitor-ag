import os
import sys
import time
import argparse
import requests
import re
from playwright.sync_api import sync_playwright
from datetime import datetime, timedelta, timezone

# 環境変数からDiscord Webhook URLを取得
DEFAULT_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
TEINE_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL_TEINE")

# 日本時間 (JST)
JST = timezone(timedelta(hours=9))

# 監視設定
STATIONS = [
    {
        "name": "発寒中央駅",
        "station_id": "088",
        "direction_name": "小樽方面",
        "panel_id": "#panelA2",
        "active_start": "17:30",
        "active_end": "19:00",
        "webhook_urls": [DEFAULT_WEBHOOK_URL]
    },
    {
        "name": "手稲駅",
        "station_id": "085",
        "direction_name": "札幌・岩見沢方面",
        "panel_id": "#panelA1",
        "active_start": "07:30",
        "active_end": "09:00",
        # 手稲はデフォルトのURLにも送りつつ、専用URLがあればそれにも送る
        "webhook_urls": [DEFAULT_WEBHOOK_URL] + ([TEINE_WEBHOOK_URL] if TEINE_WEBHOOK_URL else [])
    }
]

def send_discord_notify(webhook_url, message):
    """指定されたWebhook URLにメッセージを送信する"""
    if not webhook_url:
        return

    data = {"content": message}
    try:
        response = requests.post(webhook_url, json=data)
        response.raise_for_status()
        print(f"Notification sent successfully.")
    except Exception as e:
        print(f"Failed to send notification: {e}")

def scrape_station(page, station_config, now):
    """特定の駅・方面の運行情報をスクレイピングする"""
    url = f"https://www3.jrhokkaido.co.jp/webunkou/timetable.html?id={station_config['station_id']}"
    print(f"Checking {station_config['name']} ({station_config['direction_name']})...")
    
    page.goto(url)
    page.wait_for_load_state("networkidle")

    # タブをクリック
    try:
        tab = page.get_by_text(station_config['direction_name'])
        if tab.count() > 0:
            tab.first.click()
            page.wait_for_timeout(2000)
    except:
        pass

    start_time = now - timedelta(hours=1)
    end_time = now + timedelta(hours=1)
    
    panel = page.locator(station_config['panel_id'])
    rows = panel.locator("tr").all()
    
    alerts = []
    for row in rows:
        hour_elem = row.locator("th.hour")
        if hour_elem.count() == 0: continue
        
        hour_text = hour_elem.inner_text().strip()
        if not hour_text.isdigit(): continue
        hour = int(hour_text)
        if not (0 <= hour <= 23): continue
        
        items = row.locator("div.item").all()
        for item in items:
            min_elem = item.locator("div.min")
            if min_elem.count() == 0: continue
            
            min_text = min_elem.inner_text().strip()
            if not min_text.isdigit(): continue
            minute = int(min_text)
            
            train_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            in_range = start_time <= train_time <= end_time
            
            status = ""
            img_unkou = item.locator("img.unkou")
            if img_unkou.count() > 0:
                src = img_unkou.first.get_attribute("src") or ""
                if "mark_chien" in src: status = "⚠️ 遅延（△）"
                elif "mark_zenkyu" in src: status = "❌ 運休（✖）"
                elif "mark_bubunkyu" in src: status = "⚠️ 部分運休（✖）"
            
            if in_range:
                if status:
                    alerts.append(f"{hour:02}:{minute:02} 発 - {status}")
                # ログ出力用
                unkou_code = item.get_attribute("data-unkou")
                chien_info = item.get_attribute("data-chien")
                print(f"  [IN RANGE] {hour:02}:{minute:02} | Status: {status or f'Normal ({unkou_code}/{chien_info})'}")

    return alerts

def main():
    parser = argparse.ArgumentParser(description="JR Train Monitor")
    parser.add_argument("--test", action="store_true", help="Send a test notification")
    args = parser.parse_args()

    if args.test:
        send_discord_notify(DEFAULT_WEBHOOK_URL, "\nDiscord通知テスト: これはテストメッセージです。")
        return

    now = datetime.now(JST)
    print(f"Current JST: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    
    exec_mode = "【定期監視】" if "GITHUB_ACTIONS" in os.environ else "【ローカル実行】"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        for station in STATIONS:
            # 時間帯チェック
            start_h, start_m = map(int, station['active_start'].split(':'))
            end_h, end_m = map(int, station['active_end'].split(':'))
            active_start = now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
            active_end = now.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
            
            if not (active_start <= now <= active_end):
                print(f"Skipping {station['name']}: Out of active hours ({station['active_start']} - {station['active_end']})")
                continue
            
            station_alerts = scrape_station(page, station, now)
            if station_alerts:
                station_msg = f"\n{exec_mode} JR北海道 運行情報\n📍 {station['name']}（{station['direction_name']}）\n" + "\n".join(station_alerts)
                print(f"Irregularities found for {station['name']}! Sending to all configured webhooks...")
                for url in station['webhook_urls']:
                    send_discord_notify(url, station_msg)
            else:
                print(f"No irregularities found for {station['name']}.")

        browser.close()

if __name__ == "__main__":
    main()
