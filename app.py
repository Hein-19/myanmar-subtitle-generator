import streamlit as st
import requests
import re
import time

st.set_page_config(page_title="Myanmar SRT Subtitle Translator", page_icon="🎬")
st.title("🎬 Myanmar SRT Subtitle Generator")

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

def parse_srt_blocks(srt_text):
    """SRT ဖိုင်မှ Index, Timestamp နှင့် Dialogue စာသားများကို ခွဲထုတ်ခြင်း"""
    raw_blocks = re.split(r'\n\s*\n', srt_text.strip())
    parsed = []
    for b in raw_blocks:
        lines = [line.strip() for line in b.strip().splitlines() if line.strip()]
        if len(lines) >= 3 and "-->" in lines[1]:
            idx = lines[0]
            ts = lines[1]
            text = " ".join(lines[2:])
            parsed.append({"idx": idx, "ts": ts, "text": text})
        elif len(lines) >= 2 and "-->" in lines[0]:
            idx = str(len(parsed) + 1)
            ts = lines[0]
            text = " ".join(lines[1:])
            parsed.append({"idx": idx, "ts": ts, "text": text})
    return parsed

def chunk_list(items, size):
    return [items[i:i + size] for i in range(0, len(items), size)]

def translate_dialogues_with_retry(block_chunk, api_key, model_name, max_retries=4):
    """Timestamp မပါဘဲ [နံပါတ်] စာသား သီးသန့်ကိုသာ ဘာသာပြန်ခိုင်းပြီး မူရင်း Timestamp နှင့် ပြန်ပေါင်းခြင်း"""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://myanmar-subtitle-generator.streamlit.app",
        "X-Title": "Myanmar Subtitle Generator",
    }

    # Timestamp ဖျက်ပြီး [1] စာသား ပုံစံဖြင့်သာ ပို့ရန် ပြင်ဆင်ခြင်း
    numbered_lines = [f"[{i + 1}] {item['text']}" for i, item in enumerate(block_chunk)]
    payload_text = "\n".join(numbered_lines)

    prompt = (
        "Translate each numbered subtitle line below into natural, fluent spoken Burmese (Myanmar).\n"
        "CRITICAL RULES:\n"
        "1. Keep the exact [number] prefix at the start of every line (e.g., [1], [2], ...).\n"
        "2. Translate EVERY single line in order. Do NOT merge, skip, or add lines.\n"
        "3. Output ONLY the translated lines without any markdown code blocks or explanations.\n\n"
        f"{payload_text}"
    )

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": "You are a professional movie subtitle translator specializing in natural spoken Burmese (Myanmar)."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2
    }

    for attempt in range(max_retries):
        try:
            res = requests.post(url, headers=headers, json=payload, timeout=120)
            if res.status_code == 200:
                data = res.json()
                raw_out = data["choices"][0]["message"]["content"].strip()
                raw_out = re.sub(r'^```[a-zA-Z]*\n', '', raw_out)
                raw_out = re.sub(r'\n```$', '', raw_out).strip()

                # [1], [2] နံပါတ်အလိုက် ဘာသာပြန်စာသားများကို ပြန်ဖမ်းယူခြင်း
                trans_map = {}
                for line in raw_out.splitlines():
                    m = re.match(r'^\[(\d+)\]\s*(.+)$', line.strip())
                    if m:
                        trans_map[int(m.group(1))] = m.group(2).strip()

                # မူရင်း Timestamp များနှင့် ပြန်လည်ပေါင်းစပ်ခြင်း
                rebuilt_blocks = []
                for i, item in enumerate(block_chunk):
                    mm_text = trans_map.get(i + 1, item["text"])
                    rebuilt_blocks.append(f"{item['idx']}\n{item['ts']}\n{mm_text}")

                return "\n\n".join(rebuilt_blocks), None

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
    parsed_blocks = parse_srt_blocks(raw_srt)
    chunks = chunk_list(parsed_blocks, chunk_size)
    total_parts = len(chunks)

    st.info(f"📄 စုစုပေါင်း စာတန်း {len(parsed_blocks)} ကြောင်း ({total_parts} ပိုင်း) တွေ့ရှိပါသည်။ (Timestamp များကို ဖျက်ချန်ထားပြီး စာသားသီးသန့် ဘာသာပြန်ပေးပါမည်)")

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

                translated_srt_chunk, err = translate_dialogues_with_retry(chunk, api_key, model_name)

                if err:
                    st.error(f"API Error at part {i + 1}: {err}")
                    has_error = True
                    break

                translated_parts.append(translated_srt_chunk)
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
