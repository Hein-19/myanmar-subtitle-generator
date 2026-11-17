import streamlit as st
import requests
import re
import time

st.set_page_config(page_title="Myanmar SRT Subtitle Translator", page_icon="🎬")
st.title("🎬 Myanmar SRT Subtitle Generator")

# OpenRouter API Key (Streamlit Secrets သို့မဟုတ် Sidebar မှ ထည့်သွင်းရန်)
default_key = ""
try:
    default_key = st.secrets.get("OPENROUTER_API_KEY", "")
except Exception:
    pass

with st.sidebar:
    st.header("⚙️ Settings")
    api_key = st.text_input("OpenRouter API Key", value=default_key, type="password")
    model_name = st.selectbox(
        "Select Model",
        [
            "deepseek/deepseek-chat",
            "deepseek/deepseek-chat-v3-0324:free",
            "google/gemini-2.0-flash-exp:free",
            "qwen/qwen-2.5-72b-instruct:free",
        ],
        index=0
    )
    chunk_size = st.number_input("Subtitle blocks per chunk", min_value=20, max_value=150, value=60, step=10)
    delay_seconds = st.number_input("Delay between parts (seconds)", min_value=5, max_value=120, value=45, step=5)

def split_srt_blocks(srt_text):
    blocks = re.split(r'\n\s*\n', srt_text.strip())
    return [b.strip() for b in blocks if b.strip()]

def chunk_list(items, size):
    return [items[i:i + size] for i in range(0, len(items), size)]

def translate_chunk_with_retry(chunk_text, api_key, model_name, max_retries=4):
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://myanmar-subtitle-generator.streamlit.app",
        "X-Title": "Myanmar Subtitle Generator",
    }

    prompt = (
        "Translate the following SRT subtitle blocks into natural, fluent spoken Burmese (Myanmar). "
        "CRITICAL RULES:\n"
        "1. Keep the exact subtitle index numbers and timestamps (HH:MM:SS,mmm --> HH:MM:SS,mmm) unchanged.\n"
        "2. Translate ONLY the dialogue text into natural Burmese.\n"
        "3. Output ONLY valid SRT format without any markdown code blocks (like ```srt) or explanations.\n\n"
        f"{chunk_text}"
    )

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": "You are a professional movie subtitle translator specializing in natural Burmese (Myanmar)."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2
    }

    for attempt in range(max_retries):
        try:
            res = requests.post(url, headers=headers, json=payload, timeout=120)
            if res.status_code == 200:
                data = res.json()
                translated = data["choices"][0]["message"]["content"].strip()
                translated = re.sub(r'^```[a-zA-Z]*\n', '', translated)
                translated = re.sub(r'\n```$', '', translated).strip()
                return translated, None
            elif res.status_code == 429:
                wait_time = 50
                st.warning(f"⏳ Rate limit (429) ခဏပြည့်နေပါသည်။ စက္ကန့် {wait_time} စောင့်ပြီး ပြန်စမ်းနေပါသည်... (ကြိုးစားမှု {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
            else:
                return None, f"API Error {res.status_code}: {res.text}"
        except Exception as e:
            if attempt < max_retries - 1:
                st.warning(f"⚠️ Connection အဆင်မပြေသဖြင့် 15 စက္ကန့်စောင့်ပြီး ပြန်စမ်းနေပါသည်... ({e})")
                time.sleep(15)
            else:
                return None, str(e)

    return None, "Rate limit (429) ဆက်တိုက်ဖြစ်နေသဖြင့် ခဏနားပြီးမှ ပြန်စမ်းကြည့်ပါ။"

uploaded_file = st.file_uploader("Upload SRT Subtitle File (.srt)", type=["srt"])

if uploaded_file is not None:
    raw_srt = uploaded_file.read().decode("utf-8", errors="replace")
    blocks = split_srt_blocks(raw_srt)
    chunks = chunk_list(blocks, chunk_size)
    total_parts = len(chunks)

    st.info(f"📄 စုစုပေါင်း စာတန်း {len(blocks)} ကြောင်း ({total_parts} ပိုင်း) တွေ့ရှိပါသည်။")

    if st.button("🚀 Start Translation"):
        if not api_key:
            st.error("❌ ဘယ်ဘက် Settings ထဲတွင် OpenRouter API Key ထည့်ပေးပါ။")
        else:
            progress_bar = st.progress(0)
            status_text = st.empty()
            translated_parts = []
            has_error = False

            for i, chunk in enumerate(chunks):
                status_text.markdown(f"**Translating part {i + 1} of {total_parts}...**")
                chunk_text = "\n\n".join(chunk)

                translated_text, err = translate_chunk_with_retry(chunk_text, api_key, model_name)

                if err:
                    st.error(f"API Error at part {i + 1}: {err}")
                    has_error = True
                    break

                translated_parts.append(translated_text)
                progress_bar.progress((i + 1) / total_parts)

                # နောက်ဆုံးအပိုင်း မဟုတ်သေးပါက ၄၅ စက္ကန့် စောင့်ပေးမည်
                if i < total_parts - 1:
                    with st.spinner(f"⏳ Rate Limit မတက်စေရန် {delay_seconds} စက္ကန့် စောင့်ဆိုင်းနေပါသည်..."):
                        time.sleep(delay_seconds)

            if translated_parts:
                final_srt = "\n\n".join(translated_parts)
                output_filename = uploaded_file.name.rsplit(".", 1)[0] + "_mm.srt"

                if not has_error:
                    status_text.success("✅ ဘာသာပြန်ခြင်း အားလုံး အောင်မြင်စွာ ပြီးဆုံးပါပြီ!")
                else:
                    status_text.warning("⚠️ တစ်ဝက်တစ်ပျက် ရပ်တန့်သွားသော်လည်း ပြီးသလောက် အပိုင်းများကို Download ဆွဲယူနိုင်ပါသည်။")

                st.download_button(
                    label="📥 Download Myanmar SRT",
                    data=final_srt.encode("utf-8"),
                    file_name=output_filename,
                    mime="text/plain"
                )
