import streamlit as st
from groq import Groq
import requests
import tempfile
import os
import subprocess
import time
from datetime import timedelta

st.set_page_config(page_title="Myanmar Subtitle AI", page_icon="🎬", layout="centered")

st.markdown("""
    <style>
    .stButton>button {
        width: 100%;
        background-color: #2e7d32;
        color: white;
        font-weight: bold;
        border-radius: 8px;
    }
    </style>
""", unsafe_allow_html=True)

st.title("🎬 Myanmar Subtitle Generator & Translator")
st.write("Groq (Whisper) နှင့် Gemini AI (Chunking + Auto-Retry) သုံးပြီး Subtitle ဖန်တီးမည်")

def format_timestamp(seconds):
    td = timedelta(seconds=seconds)
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    millisecs = int((td.total_seconds() - total_seconds) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"

def json_to_srt(segments):
    srt_output = ""
    for idx, segment in enumerate(segments, start=1):
        start_val = segment.get('start', 0) if isinstance(segment, dict) else getattr(segment, 'start', 0)
        end_val = segment.get('end', 0) if isinstance(segment, dict) else getattr(segment, 'end', 0)
        text_val = segment.get('text', '') if isinstance(segment, dict) else getattr(segment, 'text', '')
        
        start_time = format_timestamp(start_val)
        end_time = format_timestamp(end_val)
        text = text_val.strip()
        srt_output += f"{idx}\n{start_time} --> {end_time}\n{text}\n\n"
    return srt_output

# Gemini ဖြင့် အပိုင်းငယ်များခွဲ၍ (Chunk size = 10) ဘာသာပြန်သည့် Function
def translate_srt_with_gemini_chunks(api_key, raw_srt, primary_model, available_models, chunk_size=10):
    blocks = [b.strip() for b in raw_srt.strip().split("\n\n") if b.strip()]
    translated_blocks = []
    
    total_blocks = len(blocks)
    progress_bar = st.progress(0)
    status_text = st.empty()

    models_to_try = [primary_model] + [m for m in available_models if m != primary_model]

    for i in range(0, total_blocks, chunk_size):
        chunk_blocks = blocks[i:i + chunk_size]
        chunk_text = "\n\n".join(chunk_blocks)
        
        progress_percent = min(1.0, (i + chunk_size) / total_blocks)
        status_text.text(f"Gemini ဖြင့် ဘာသာပြန်နေစဉ်... အပိုင်း ({i+1} မှ {min(i+1+chunk_size, total_blocks)} / {total_blocks} စာကြောင်းများ)")
        progress_bar.progress(progress_percent)

        prompt = f"""You are a professional subtitle translator. 
Translate the following SRT content into natural and fluent Burmese (Myanmar language).

STRICT RULES:
1. Keep the SRT structure, sequence numbers, and timecodes EXACTLY the same.
2. Only translate the text lines, do not alter timestamps.
3. Use natural spoken Burmese suitable for movie subtitles.

SRT Content:
{chunk_text}"""

        chunk_success = False
        last_err = ""

        for model_name in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key.strip()}"
            headers = {'Content-Type': 'application/json'}
            payload = {
                "contents": [{"parts": [{"text": prompt}]}]
            }

            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = requests.post(url, headers=headers, json=payload, timeout=60)
                    res_json = response.json()
                    
                    if response.status_code == 200:
                        translated_chunk = res_json['candidates'][0]['content']['parts'][0]['text'].strip()
                        translated_blocks.append(translated_chunk)
                        chunk_success = True
                        break
                    
                    err_msg = res_json.get('error', {}).get('message', 'Unknown Error')
                    last_err = err_msg
                    
                    if any(kw in err_msg.lower() for kw in ["high demand", "resource_exhausted", "quota", "503", "429", "temporary"]):
                        if attempt < max_retries - 1:
                            wait_sec = (attempt + 1) * 3
                            time.sleep(wait_sec)
                            continue
                    break
                except Exception as e:
                    last_err = str(e)
                    time.sleep(2)
            
            if chunk_success:
                break
        
        if not chunk_success:
            raise Exception(f"Gemini API Chunk Error at block {i+1}: {last_err}")

    progress_bar.empty()
    status_text.empty()
    return "\n\n".join(translated_blocks) + "\n\n"

# Sidebar - API Keys Setup
st.sidebar.header("🔑 API Keys")
groq_api_key = st.sidebar.text_input("Groq API Key (Whisper အတွက်)", type="password")
gemini_api_key = st.sidebar.text_input("Gemini API Key (ဘာသာပြန်ရန်)", type="password")

# API Key ရှိပါက ရရှိနိုင်သော Models များကို လှမ်းယူခြင်း
available_models = []
if gemini_api_key:
    try:
        list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={gemini_api_key.strip()}"
        res = requests.get(list_url, timeout=10)
        if res.status_code == 200:
            models_data = res.json().get('models', [])
            for m in models_data:
                if 'generateContent' in m.get('supportedGenerationMethods', []):
                    available_models.append(m['name'].replace('models/', ''))
    except Exception:
        pass

selected_model = None
if available_models:
    selected_model = st.sidebar.selectbox("🤖 Gemini Model ကို ရွေးပါ", available_models)

uploaded_file = st.file_uploader("ဗီဒီယို သို့မဟုတ် အသံဖိုင် တင်ပါ (mp3, wav, mp4, m4a)", type=["mp3", "wav", "mp4", "m4a"])

if uploaded_file:
    if not groq_api_key or not gemini_api_key:
        st.warning("⚠️ ကျေးဇူးပြု၍ ဘယ်ဘက် Sidebar တွင် API Keys နှစ်ခုလုံး ဖြည့်သွင်းပါ။")
    elif not selected_model:
        st.warning("⚠️ ကျေးဇူးပြု၍ Gemini API Key ကို မှန်ကန်စွာ ဖြည့်သွင်းပါ။")
    else:
        if st.button("🚀 Subtitle ထုတ်ပြီး Gemini ဖြင့် အပိုင်းလိုက် ဘာသာပြန်မည်"):
            with st.spinner("ဖိုင်ကို Processing လုပ်နေပါသည်..."):
                
                file_ext = os.path.splitext(uploaded_file.name)[1].lower()
                with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_file:
                    tmp_file.write(uploaded_file.read())
                    tmp_file_path = tmp_file.name

                audio_path = tmp_file_path
                compressed_audio_path = None

                try:
                    if os.path.getsize(tmp_file_path) > 24 * 1024 * 1024:
                        st.info("ဖိုင်ဆိုဒ်ကြီးသောကြောင့် အသံဖိုင်အဖြစ် ပြောင်းလဲချုံ့နေပါသည်...")
                        compressed_audio_path = tmp_file_path + "_compressed.mp3"
                        cmd = [
                            "ffmpeg", "-y", "-i", tmp_file_path,
                            "-vn", "-acodec", "libmp3lame", "-b:a", "64k",
                            compressed_audio_path
                        ]
                        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        audio_path = compressed_audio_path

                    # ၁။ Groq Whisper ဖြင့် Subtitle ထုတ်ယူခြင်း
                    st.info("🎙️ Groq Whisper ဖြင့် အသံများကို စာသားအဖြစ် ပြောင်းလဲနေပါသည်...")
                    groq_client = Groq(api_key=groq_api_key.strip())
                    with open(audio_path, "rb") as file:
                        transcription = groq_client.audio.transcriptions.create(
                            file=(audio_path, file.read()),
                            model="whisper-large-v3",
                            response_format="verbose_json"
                        )
                    segments = transcription.segments if hasattr(transcription, 'segments') else transcription.get('segments', [])
                    raw_srt = json_to_srt(segments)

                    # ၂။ Gemini ဖြင့် အပိုင်းငယ်များခွဲ၍ (Chunk size = 10) ဘာသာပြန်ခြင်း
                    translated_srt = translate_srt_with_gemini_chunks(
                        gemini_api_key, raw_srt, selected_model, available_models, chunk_size=10
                    )

                    st.success("🎉 ဘာသာပြန်ခြင်း အောင်မြင်ပါသည်!")
                    
                    st.download_button(
                        label="📥 မြန်မာ Subtitle (.srt) ဒေါင်းလုဒ်ဆွဲရန်",
                        data=translated_srt,
                        file_name="burmese_subtitles.srt",
                        mime="text/plain"
                    )
                    
                    with st.expander("စာသား ကြည့်ရှုရန်"):
                        st.text_area("Translated SRT Output", translated_srt, height=300)

                except Exception as e:
                    st.error(f"Error ဖြစ်ပွားပါသည်: {str(e)}")
                
                finally:
                    if os.path.exists(tmp_file_path):
                        os.remove(tmp_file_path)
                    if compressed_audio_path and os.path.exists(compressed_audio_path):
                        os.remove(compressed_audio_path)
