"""연프로 피드 JSON 생성"""
import json, sqlite3, os, re

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "yeonpro.db")
FEED_PATH = os.path.join(os.path.dirname(__file__), "data", "feed.json")

SHOWS_META = {
    "솔로지옥": {"icon": "🏝️", "color": "#FF6B35", "en": "Singles Inferno"},
    "하트시그널": {"icon": "💓", "color": "#FF2D55", "en": "Heart Signal"},
    "나는솔로": {"icon": "🌹", "color": "#C0392B", "en": "I Am Solo"},
    "환승연애": {"icon": "🔄", "color": "#8E44AD", "en": "EXchange"},
}

def season_sort_key(s):
    num = re.search(r'(\d+)', s.get("season","") or "")
    return int(num.group(1)) if num else 0

def export():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    feed = {"shows": {}}

    for show_name, meta in SHOWS_META.items():
        videos = [dict(r) for r in conn.execute("""
            SELECT video_id, channel_name, title, published_at,
                   view_count, like_count, comment_count, duration_sec,
                   thumbnail_url, season, episode, content_type
            FROM videos WHERE show_name = ? AND view_count >= 1000
            ORDER BY view_count DESC LIMIT 800
        """, (show_name,)).fetchall()]

        for v in videos:
            v["embed_url"] = f"https://www.youtube.com/embed/{v['video_id']}"

        # 시즌 목록
        seasons = [dict(r) for r in conn.execute("""
            SELECT season, COUNT(*) as cnt, SUM(view_count) as views
            FROM videos WHERE show_name = ? AND season IS NOT NULL AND view_count >= 1000
            GROUP BY season
        """, (show_name,)).fetchall()]
        seasons.sort(key=season_sort_key, reverse=True)

        feed["shows"][show_name] = {
            **meta,
            "total": len(videos),
            "seasons": seasons,
            "videos": videos,
        }

    conn.close()

    with open(FEED_PATH, "w", encoding="utf-8") as f:
        json.dump(feed, f, ensure_ascii=False, indent=2)

    total = sum(s["total"] for s in feed["shows"].values())
    print(f"✅ 피드 생성: 총 {total}개")
    for name, data in feed["shows"].items():
        print(f"  {data['icon']} {name}: {data['total']}개 | 시즌 {len(data['seasons'])}개")

if __name__ == "__main__":
    export()
