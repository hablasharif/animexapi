import re, json, urllib.request
import streamlit as st

SITE = "https://animex.one"
API  = "https://pp.animex.one/rest/api"
UA   = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

def fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Origin": SITE, "Referer": f"{SITE}/", "Accept": "*/*"
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read()

def resolve(watch_url):
    m = re.search(r"/watch/.+-(\d+)-episode-(\d+)", watch_url)
    if not m:
        return None, None, "Invalid URL format"
    anilist_id, episode = m.group(1), m.group(2)

    html = fetch(watch_url).decode("utf-8", errors="replace")
    aid_m = re.search(rf"animeId\s*:\s*['\"]([^'\"]+)['\"].{{0,200}}?anilistId\s*:\s*{anilist_id}\b", html) \
         or re.search(rf"anilistId\s*:\s*{anilist_id}\b.{{0,200}}?animeId\s*:\s*['\"]([^'\"]+)['\"]", html)
    if not aid_m:
        return None, None, "Could not find anime API ID in page"
    anime_id = aid_m.group(1)

    servers = json.loads(fetch(f"{API}/servers?id={anime_id}&epNum={episode}"))

    streams = []
    for typ, key in (("sub", "subProviders"), ("dub", "dubProviders")):
        for p in servers.get(key, []):
            try:
                data = json.loads(fetch(f"{API}/sources?id={anime_id}&epNum={episode}&type={typ}&providerId={p['id']}"))
                for s in data.get("sources", []):
                    streams.append({
                        "type": typ,
                        "provider": p["id"],
                        "url": s["url"],
                        "quality": s.get("quality", "auto"),
                        "mimetype": s.get("type", "")
                    })
            except Exception as e:
                streams.append({"type": typ, "provider": p["id"], "error": str(e)})

    return anime_id, streams, None


# --- Streamlit UI ---
st.set_page_config(page_title="AnimeX Stream Resolver", page_icon="🎬", layout="wide")
st.title("🎬 AnimeX Stream Resolver")
st.caption("Resolves animex.one watch URLs to direct HLS stream URLs")

url = st.text_input(
    "Watch URL",
    value="https://animex.one/watch/naruto-shippuden-1735-episode-3",
    placeholder="https://animex.one/watch/<slug>-<id>-episode-<ep>"
)

if st.button("Resolve Streams", type="primary"):
    with st.spinner("Fetching streams..."):
        try:
            anime_id, streams, error = resolve(url)
            if error:
                st.error(error)
            else:
                st.success(f"✅ Resolved `{anime_id}`  —  {len(streams)} stream(s) found")

                # --- raw JSON output (API-style) ---
                with st.expander("📦 Raw JSON (API response)", expanded=True):
                    st.json(streams)

                st.divider()

                # --- grouped cards ---
                sub_streams = [s for s in streams if s.get("type") == "sub"]
                dub_streams = [s for s in streams if s.get("type") == "dub"]

                col1, col2 = st.columns(2)

                for col, group, label in ((col1, sub_streams, "🔤 SUB"), (col2, dub_streams, "🔊 DUB")):
                    with col:
                        st.subheader(label)
                        for s in group:
                            with st.container(border=True):
                                if "error" in s:
                                    st.error(f"**{s['provider']}** — {s['error']}")
                                else:
                                    st.markdown(f"**Provider:** `{s['provider']}`")
                                    st.markdown(f"**Quality:** `{s['quality']}`")
                                    st.markdown(f"**Type:** `{s['mimetype']}`")
                                    st.code(s["url"], language=None)

        except Exception as e:
            st.error(f"Error: {e}")