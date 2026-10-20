from datetime import timedelta
import os
import subprocess
import tempfile
import time
from groq import Groq
import requests
import streamlit as st

st.set_page_config(
    page_title="Myanmar Subtitle AI", page_icon="🎬", layout="centered"
)

st.markdown(
    """
    <style>
    .stButton>button {
        width: 100%;
        background-color: #2e7d32;
        color: white;
        font-weight: bold;
        border-radius: 8px;
    }
    </style>
""",
    unsafe_allow_html=True,
)

st.title("🎬 Myanmar Subtitle Generator & Translator")
st.write(
    "Groq (Whisper) နှင့် Gemini AI (Chunking 10 + Paced Rate Limit) သုံးပြီး"
    " Subtitle ဖန်တီးမည်"
)

# 🧠 Session State (ဒေါင်းလုဒ်ခလုတ်နှိပ်လျှင် ပျောက်မသွားစေရန်)
if "raw_srt" not in st.session_state:
  st.session_state.raw_srt = None
if "translated_srt" not in st.session_state:
  st.session_state.translated_srt = None


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
    start_val = (
        segment.get("start", 0)
        if isinstance(segment, dict)
        else getattr(segment, "start", 0)
    )
    end_val = (
        segment.get("end", 0)
        if isinstance(segment, dict)
        else getattr(segment, "end", 0)
    )
    text_val = (
        segment.get("text", "")
        if isinstance(segment, dict)
        else getattr(segment, "text", "")
    )

    start_time = format_timestamp(start_val)
    end_time = format_timestamp(end_val)
    text = text_val.strip()
    srt_output += f"{idx}\n{start_time} --> {end_time}\n{text}\n\n"
  return srt_output


# Gemini ဖြင့် ၁၀ ကြောင်းစီ ခွဲ၍ ဘာသာပြန်သည့် Function
def translate_srt_with_gemini_chunks(
    api_keys, raw_srt, primary_model, available_models, chunk_size=10
):
  blocks = [b.strip() for b in raw_srt.strip().split("\n\n") if b.strip()]
  translated_blocks = []

  total_blocks = len(blocks)
  progress_bar = st.progress(0)
  status_placeholder = st.empty()

  models_to_try = [primary_model] + [
      m for m in available_models if m != primary_model
  ]
  current_key_idx = 0

  for i in range(0, total_blocks, chunk_size):
    chunk_blocks = blocks[i : i + chunk_size]
    chunk_text = "\n\n".join(chunk_blocks)

    start_block = i + 1
    end_block = min(i + chunk_size, total_blocks)

    prompt = f"""You are a professional subtitle translator.
Translate the following SRT content into natural and fluent Burmese (Myanmar language).

STRICT RULES:
1. Keep the SRT structure, sequence numbers, and timecodes EXACTLY the same.
2. Only translate the text lines, do not alter timestamps.
3. Use natural spoken Burmese suitable for movie subtitles.
4. If a sentence is long, wrap it into two lines using a single newline (\\n) for readability.

SRT Content:
{chunk_text}"""

    chunk_success = False

    while not chunk_success:
      progress_percent = min(1.0, (i + chunk_size) / total_blocks)
      progress_bar.progress(progress_percent)
      status_placeholder.info(
          f"Gemini ဖြင့် ဘာသာပြန်နေစဉ်... အပိုင်း ({start_block} မှ"
          f" {end_block} / {total_blocks} စာကြောင်းများ)"
      )

      active_key = api_keys[current_key_idx]

      for model_name in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={active_key.strip()}"
        headers = {"Content-Type": "application/json"}
        payload = {"contents": [{"parts": [{"text": prompt}]}]}

        try:
          response = requests.post(
              url, headers=headers, json=payload, timeout=60
          )
          res_json = response.json()

          if response.status_code == 200:
            translated_chunk = (
                res_json["candidates"][0]["content"]["parts"][0]["text"].strip()
            )
            translated_blocks.append(translated_chunk)
            chunk_success = True

            # 15 RPM ပြည့်မသွားစေရန် တည်ငြိမ်သော ၄.၅ စက္ကန့် ပုံမှန်အနားပေးခြင်း
            time.sleep(4.5)
            break

          err_msg = (
              res_json.get("error", {}).get("message", "").lower()
              + f" (Status: {response.status_code})"
          )

          # Quota / Rate Limit (429) ဖြစ်ပါက အခြား Key ရှိလျှင် ချက်ချင်း လှည့်သုံးခြင်း
          if any(
              kw in err_msg
              for kw in [
                  "quota",
                  "429",
                  "resource_exhausted",
                  "rate",
                  "high demand",
              ]
          ):
            if len(api_keys) > 1:
              current_key_idx = (current_key_idx + 1) % len(api_keys)
              status_placeholder.warning(
                  f"🔄 Key {current_key_idx+1} သို့ ပြောင်းလဲ၍ ဆက်လက်"
                  " ကြိုးစားနေပါသည်..."
              )
              time.sleep(2)
              break

            # Key ၁ ခုတည်း ဖြစ်ပါက ၆၀ စက္ကန့် Countdown စောင့်ဆိုင်းခြင်း
            for remaining in range(60, 0, -1):
              status_placeholder.warning(
                  f"⏳ Gemini Rate Limit ခေတ္တပြည့်သွားပါသဖြင့် စက္ကန့် {remaining}"
                  f" စောင့်ဆိုင်းနေပါသည်... စက္ကန့်ပြည့်ပါက အပိုင်း ({start_block}"
                  f" မှ {end_block}) ကို ဆက်လက် ဘာသာပြန်ပါမည်။"
              )
              time.sleep(1)

            status_placeholder.info(
                f"🔄 အပိုင်း ({start_block}) ကို ပြန်လည် စတင်နေပါသည်..."
            )
            break

        except Exception:
          time.sleep(3)

  progress_bar.empty()
  status_placeholder.empty()
  return "\n\n".join(translated_blocks) + "\n\n"


# 🔒 Secrets မှ API Keys များ ခေါ်ယူခြင်း (ကော်မာခံ၍ Key အများအပြား ထည့်နိုင်ပါသည်)
try:
  GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
  gemini_raw_keys = st.secrets["GEMINI_API_KEY"]
  # ကော်မာ ပါပါက list ခွဲထုတ်ခြင်း၊ မပါပါက single key အဖြစ် ယူခြင်း
  GEMINI_API_KEYS = [
      k.strip() for k in gemini_raw_keys.split(",") if k.strip()
  ]
except Exception:
  st.error(
      "⚠️ Streamlit Secrets ထဲတွင် API Keys များ တွေ့မရှိပါ။ .streamlit/secrets.toml"
      " ဖိုင်ကို စစ်ဆေးပါ။"
  )
  st.stop()

# ပထမဆုံး Key ဖြင့် ရရှိနိုင်သော Models များကို ခေါ်ယူခြင်း
available_models = []
if GEMINI_API_KEYS:
  try:
    list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEYS[0]}"
    res = requests.get(list_url, timeout=10)
    if res.status_code == 200:
      models_data = res.json().get("models", [])
      for m in models_data:
        if "generateContent" in m.get("supportedGenerationMethods", []):
          available_models.append(m["name"].replace("models/", ""))
  except Exception:
    pass

selected_model = None
if available_models:
  # gemini-2.5-flash သို့မဟုတ် gemini-1.5-flash ကို default ရွေးပေးခြင်း
  default_index = 0
  for i, m in enumerate(available_models):
    if "flash" in m.lower() and "lite" not in m.lower():
      default_index = i
      break
  selected_model = st.sidebar.selectbox(
      "🤖 Gemini Model ကို ရွေးပါ", available_models, index=default_index
  )

uploaded_file = st.file_uploader(
    "ဗီဒီယို သို့မဟုတ် အသံဖိုင် တင်ပါ (mp3, wav, mp4, m4a)",
    type=["mp3", "wav", "mp4", "m4a"],
)

if uploaded_file:
  if not GROQ_API_KEY or not GEMINI_API_KEYS:
    st.warning("⚠️ ကျေးဇူးပြု၍ Streamlit Secrets တွင် API Keys များကို ထည့်သွင်းပါ။")
  elif not selected_model:
    st.warning("⚠️ ကျေးဇူးပြု၍ Gemini API Key ကို မှန်ကန်စွာ ဖြည့်သွင်းပါ။")
  else:
    if st.button("🚀 Subtitle ထုတ်ပြီး Gemini ဖြင့် အပိုင်းလိုက် ဘာသာပြန်မည်"):
      with st.spinner("ဖိုင်ကို Processing လုပ်နေပါသည်..."):

        file_ext = os.path.splitext(uploaded_file.name)[1].lower()
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=file_ext
        ) as tmp_file:
          tmp_file.write(uploaded_file.read())
          tmp_file_path = tmp_file.name

        audio_path = tmp_file_path
        compressed_audio_path = None

        try:
          if os.path.getsize(tmp_file_path) > 24 * 1024 * 1024:
            st.info(
                "ဖိုင်ဆိုဒ်ကြီးသောကြောင့် အသံဖိုင်အဖြစ် ပြောင်းလဲချုံ့နေပါသည်..."
            )
            compressed_audio_path = tmp_file_path + "_compressed.mp3"
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                tmp_file_path,
                "-vn",
                "-acodec",
                "libmp3lame",
                "-b:a",
                "64k",
                compressed_audio_path,
            ]
            subprocess.run(
                cmd,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            audio_path = compressed_audio_path

          # ၁။ Groq Whisper ဖြင့် Subtitle ထုတ်ယူခြင်း
          st.info(
              "🎙️ Groq Whisper ဖြင့် အသံများကို စာသားအဖြစ် ပြောင်းလဲနေပါသည်..."
          )
          groq_client = Groq(api_key=GROQ_API_KEY.strip())
          with open(audio_path, "rb") as file:
            transcription = groq_client.audio.transcriptions.create(
                file=(audio_path, file.read()),
                model="whisper-large-v3",
                response_format="verbose_json",
            )
          segments = (
              transcription.segments
              if hasattr(transcription, "segments")
              else transcription.get("segments", [])
          )

          st.session_state.raw_srt = json_to_srt(segments)

          # ၂။ Gemini ဖြင့် ၁၀ ကြောင်းစီ ခွဲ၍ ဘာသာပြန်ခြင်း (chunk_size=10)
          st.session_state.translated_srt = translate_srt_with_gemini_chunks(
              GEMINI_API_KEYS,
              st.session_state.raw_srt,
              selected_model,
              available_models,
              chunk_size=10,
          )

        except Exception as e:
          st.error(f"Error ဖြစ်ပွားပါသည်: {str(e)}")

        finally:
          if os.path.exists(tmp_file_path):
            os.remove(tmp_file_path)
          if compressed_audio_path and os.path.exists(compressed_audio_path):
            os.remove(compressed_audio_path)

# 📥 ဒေါင်းလုဒ် ခလုတ်များ
if st.session_state.raw_srt and st.session_state.translated_srt:
  st.success("🎉 ဘာသာပြန်ခြင်း အောင်မြင်ပါသည်!")

  col1, col2 = st.columns(2)
  with col1:
    st.download_button(
        label="📥 မူရင်း SRT (.srt) ဒေါင်းလုဒ်",
        data=st.session_state.raw_srt,
        file_name="original_subtitles.srt",
        mime="text/plain",
        key="btn_dl_raw",
    )
  with col2:
    st.download_button(
        label="📥 မြန်မာ SRT (.srt) ဒေါင်းလုဒ်",
        data=st.session_state.translated_srt,
        file_name="burmese_subtitles.srt",
        mime="text/plain",
        key="btn_dl_trans",
    )

  with st.expander("စာသားများ အစမ်းကြည့်ရှုရန်"):
    tab1, tab2 = st.tabs(["🇲🇲 မြန်မာဘာသာပြန်", "🇬🇧 မူရင်းစာတန်း"])
    with tab1:
      st.text_area(
          "Translated Output",
          st.session_state.translated_srt,
          height=250,
          key="tab_translated",
      )
    with tab2:
      st.text_area(
          "Original Output",
          st.session_state.raw_srt,
          height=250,
          key="tab_original",
      )
