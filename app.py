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
    
""", unsafe_allow_html=True)

st.title("🎬 Myanmar Subtitle Generator & Translator")
st.write("ကြိုက်နှစ်သက်ရာ နည်းလမ်းနှင့် Gemini မော်ဒယ်ကို စိတ်ကြိုက်ရွေးချယ်နိုင်သော Subtitle စနစ်")

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
    total_segs = len(segments)
    
    for idx, segment in enumerate(segments, start=1):
        start_val = segment.get('start', 0) if isinstance(segment, dict) else getattr(segment, 'start', 0)
        end_val = segment.get('end', 0) if isinstance(segment, dict) else getattr(segment, 'end', 0)
        text_val = segment.get('text', '') if isinstance(segment, dict) else getattr(segment, 'text', '')
        text = text_val.strip()

        if idx > 1:
            start_val = start_val + 0.1

        duration = end_val - start_val
        text_len = len(text)
        estimated_max_time = max(2.0, min(text_len * 0.15, 5.0))
        
        if duration > 6.0 and text_len < 60:
            end_val = start_val + estimated_max_time

        if idx < total_segs:
            next_seg = segments[idx]
            next_start = next_seg.get('start', 0) if isinstance(next_seg, dict) else getattr(next_seg, 'start', 0)
            if end_val > next_start:
                end_val = max(start_val + 1.0, next_start - 0.1)

        start_time = format_timestamp(start_val)
        end_time = format_timestamp(end_val)
        
        srt_output += f"{idx}\n{start_time} --> {end_time}\n{text}\n\n"
        
    return srt_output

# Groq + Gemini Chunking Translation Function
def translate_srt_with_gemini_chunks(api_key, raw_srt, primary_model, chunk_size=25):
    blocks = [b.strip() for b in raw_srt.strip().split("\n\n") if b.strip()]
    translated_blocks = []
    
    total_blocks = len(blocks)
    progress_bar = st.progress(0)
    status_text = st.empty()

    for i in range(0, total_blocks, chunk_size):
        chunk_blocks = blocks[i:i + chunk_size]
        chunk_text = "\n\n".join(chunk_blocks)
        
        progress_percent = min(1.0, (i + chunk_size) / total_blocks)
        status_text.text(f"Gemini ({primary_model}) ဖြင့် ဘာသာပြန်နေစဉ်... အပိုင်း ({i+1} မှ {min(i+1+chunk_size, total_blocks)} / {total_blocks})")
        progress_bar.progress(progress_percent)

        prompt = f"""You are a professional subtitle translator. 
Translate the following SRT content into natural and fluent Burmese (Myanmar language).

STRICT RULES:
1. Keep the SRT structure, sequence numbers, and timecodes EXACTLY the same.
2. Only translate the text lines, do not alter timestamps.
3. Use natural spoken Burmese suitable for movie subtitles.

SRT Content:
{chunk_text}"""

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{primary_model}:generateContent?key={api_key.strip()}"
        headers = {'Content-Type': 'application/json'}
        payload = {"contents": [{"parts": [{"text": prompt}]}]}

        chunk_success = False
        last_err = ""
        for attempt in range(3):
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
                if attempt < 2:
                    time.sleep((attempt + 1) * 2)
                    continue
                break
            except Exception as e:
                last_err = str(e)
                time.sleep(2)
        
        if not chunk_success:
            raise Exception(f"Gemini API Chunk Error at block {i+1}: {last_err}")

    progress_bar.empty()
    status_text.empty()
    return "\n\n".join(translated_blocks) + "\n\n"

# Gemini Only Audio Transcription & Translation Function
def transcribe_and_translate_with_gemini(api_key, audio_path, model_name):
    upload_url = f"https://generativelanguage.googleapis.com/upload/v1beta/files?key={api_key.strip()}"
    mime_type = "audio/mp3" if audio_path.endswith(".mp3") else "audio/wav"
    
    with open(audio_path, "rb") as f:
        file_bytes = f.read()
        
    headers = {"X-Goog-Upload-Protocol": "raw", "Content-Type": mime_type}
    res = requests.post(upload_url, headers=headers, data=file_bytes, timeout=120)
    if res.status_code != 200:
        raise Exception(f"Gemini File Upload Error: {res.text}")
        
    file_info = res.json().get("file", {})
    file_uri = file_info.get("uri")
    
    gen_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key.strip()}"
    
    prompt = """You are a professional audio transcription and subtitle translation expert.
Listen to this audio file carefully. Transcribe the spoken words into accurate time-coded SRT format, and directly translate the text into natural, fluent Burmese (Myanmar language).

STRICT RULES:
1. Output MUST be in standard SRT format (sequence number, timecode format like 00:00:01,000 --> 00:00:04,000, and translated Burmese text).
2. Keep timecodes accurate to the audio.
3. Do not include markdown code block syntax (like ```srt) or any extra introductory text. Output ONLY the raw SRT text."""

    payload = {
        "contents": [
            {
                "parts": [
                    {"fileData": {"mimeType": mime_type, "fileUri": file_uri}},
                    {"text": prompt}
                ]
            }
        ]
    }
    
    response = requests.post(gen_url, headers={"Content-Type": "application/json"}, json=payload, timeout=300)
    if response.status_code != 200:
        raise Exception(f"Gemini Audio Processing Error: {response.text}")
        
    res_json = response.json()
    try:
        raw_text = res_json['candidates'][0]['content']['parts'][0]['text'].strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("srt"):
                raw_text = raw_text[3:].strip()
        return raw_text.strip() + "\n\n"
    except Exception as e:
        raise Exception(f"Failed to parse Gemini Audio response: {str(e)}")

# --- SIDEBAR SETTINGS ---
st.sidebar.header("🛠️ လုပ်ဆောင်မည့် နည်းလမ်း (Mode)")

mode_choice = st.sidebar.radio(
    "အသုံးပြုလိုသည့် နည်းလမ်းကို ရွေးပါ",
    (
        "1. Groq (Whisper) + Gemini (Translation)",
        "2. Gemini Only (Audio to Subtitle နေဖြင့် တိုက်ရိုက်)"
    )
)

st.sidebar.markdown("---")
st.sidebar.header("🔑 API Keys & Models")

# Groq Key (Mode 1 ဖြစ်မှ တောင်းမည်)
groq_api_key = ""
if "1. Groq" in mode_choice:
    groq_api_key = st.sidebar.text_input("Groq API Key ထည့်ရန်", type="password")

gemini_api_key = st.sidebar.text_input("Gemini API Key ထည့်ရန်", type="password")

# Gemini Models စုံလင်စွာ ရွေးချယ်နိုင်ရန်
default_models = [
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash", 
    "gemini-2.5-pro", 
    "gemini-2.0-flash", 
    "gemini-1.5-flash", 
    "gemini-1.5-pro"
]

available_models = default_models.copy()
if gemini_api_key:
    try:
        list_url = f"[https://generativelanguage.googleapis.com/v1beta/models?key=](https://generativelanguage.googleapis.com/v1beta/models?key=){gemini_api_key.strip()}"
        res = requests.get(list_url, timeout=5)
        if res.status_code == 200:
            models_data = res.json().get('models', [])
            fetched = []
            for m in models_data:
                if 'generateContent' in m.get('supportedGenerationMethods', []):
                    model_name = m['name'].replace('models/', '')
                    if model_name not in fetched:
                        fetched.append(model_name)
            if fetched:
                available_models = fetched
    except Exception:
        pass

selected_model = st.sidebar.selectbox("🤖 Gemini Model ကို ရွေးချယ်ပါ", available_models)

# --- MAIN UI ---
uploaded_file = st.file_uploader("ဗီဒီယို သို့မဟုတ် အသံဖိုင် တင်ပါ (mp3, wav, mp4, m4a)", type=["mp3", "wav", "mp4", "m4a"])

if uploaded_file:
    if "1. Groq" in mode_choice and (not groq_api_key or not gemini_api_key):
        st.warning("⚠️ ကျေးဇူးပြု၍ Groq API Key နှင့် Gemini API Key နှစ်ခုလုံး ဖြည့်သွင်းပါ။")
    elif "2. Gemini Only" in mode_choice and not gemini_api_key:
        st.warning("⚠️ ကျေးဇူးပြု၍ Gemini API Key ဖြည့်သွင်းပါ။")
    else:
        btn_label = "🚀 Groq + Gemini ဖြင့် Subtitle ထုတ်မည်" if "1. Groq" in mode_choice else "🚀 Gemini ဖြင့် အသံဖိုင်မှ Subtitle တိုက်ရိုက်ထုတ်မည်"
        
        if st.button(btn_label):
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

                    if "1. Groq" in mode_choice:
                        st.info("🎙️ Groq Whisper ဖြင့် အသံများကို စာသားအဖြစ် ပြောင်းလဲနေပါသည်...")
                        groq_client = Groq(api_key=groq_api_key.strip())
                        with open(audio_path, "rb") as file:
                            transcription = groq_client.audio.transcriptions.create(
                                file=(audio_path, file.read()),
                                model="whisper-large-v3",
                                response_format="verbose_json",
                                temperature=0.0
                            )
                        segments = transcription.segments if hasattr(transcription, 'segments') else transcription.get('segments', [])
                        raw_srt = json_to_srt(segments)

                        translated_srt = translate_srt_with_gemini_chunks(
                            gemini_api_key, raw_srt, selected_model, chunk_size=25
                        )
                    else:
                        st.info("🎧 Gemini ဖြင့် အသံဖိုင်ကို တိုက်ရိုက်နားထောင်၍ စာသားပြောင်းခြင်းနှင့် ဘာသာပြန်ခြင်း ဆောင်ရွက်နေပါသည်...")
                        translated_srt = transcribe_and_translate_with_gemini(
                            gemini_api_key, audio_path, selected_model
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
