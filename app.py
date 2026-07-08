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

def get_anime_id(anilist_id):
    """Search the AnimeX API for the internal anime_id using AniList ID."""
    search_url = f"{API}/search?anilistId={anilist_id}"
    try:
        data = json.loads(fetch(search_url))
        # Try direct anilistId lookup first
        if isinstance(data, dict) and data.get("id"):
            return data["id"], None
        if isinstance(data, list) and data:
            return data[0]["id"], None
    except Exception:
        pass

    # Fallback: build a watch URL from anilist ID and scrape the page
    # We need a slug — search by anilist ID via the info endpoint
    try:
        info_url = f"{API}/info?anilistId={anilist_id}"
        data = json.loads(fetch(info_url))
        anime_id = data.get("id") or data.get("animeId")
        if anime_id:
            return anime_id, None
    except Exception:
        pass

    return None, "Could not resolve internal anime ID from AniList ID. The site may require a slug-based lookup."

def resolve(anilist_id, episode):
    anime_id, error = get_anime_id(anilist_id)
    if error:
        return None, None, error

    servers = json.loads(fetch(f"{API}/servers?id={anime_id}&epNum={episode}"))
    streams = []
    for typ, key in (("sub", "subProviders"), ("dub", "dubProviders")):
        for p in servers.get(key, []):
            try:
                data = json.loads(fetch(
                    f"{API}/sources?id={anime_id}&epNum={episode}&type={typ}&providerId={p['id']}"
                ))
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
st.caption("Enter an AniList ID and episode number to get direct HLS stream URLs")

col1, col2 = st.columns([2, 1])
with col1:
    anilist_id = st.text_input("AniList ID", value="1735", placeholder="e.g. 1735")
with col2:
    episode = st.text_input("Episode", value="3", placeholder="e.g. 3")

if st.button("Resolve Streams", type="primary"):
    if not anilist_id or not episode:
        st.warning("Please enter both an AniList ID and episode number.")
    else:
        with st.spinner("Fetching streams..."):
            try:
                anime_id, streams, error = resolve(anilist_id.strip(), episode.strip())
                if error:
                    st.error(error)
                    st.info("💡 Tip: You can find the AniList ID in the URL on anilist.co — e.g. anilist.co/anime/**1735**/Naruto-Shippuden")
                else:
                    st.success(f"✅ Resolved `{anime_id}`  —  {len(streams)} stream(s) found")

                    with st.expander("📦 Raw JSON (API response)", expanded=True):
                        st.json(streams)

                    st.divider()

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