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
    "Groq (Whisper) နှင့် Gemini AI သုံးပြီး အမြန်ဆုံးနှင့် အတိကျဆုံး မြန်မာ"
    " စာတန်းထိုးများ ဖန်တီးမည်"
)

# 🔒 Streamlit Secrets မှ API Keys များကို ခေါ်ယူခြင်း
try:
  GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
  GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except Exception:
  st.error(
      "⚠️ Streamlit Secrets ထဲတွင် API Keys များ တွေ့မရှိပါ။ .streamlit/secrets.toml"
      " ဖိုင်ကို စစ်ဆေးပါ။"
  )
  st.stop()


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


# Gemini ဖြင့် အပိုင်းငယ်များခွဲ၍ မြန်ဆန်တိကျစွာ ဘာသာပြန်သည့် Function
def translate_srt_with_gemini_chunks(
    api_key, raw_srt, primary_model, available_models, chunk_size=10
):
  blocks = [b.strip() for b in raw_srt.strip().split("\n\n") if b.strip()]
  translated_blocks = []

  total_blocks = len(blocks)
  progress_bar = st.progress(0)
  status_text = st.empty()

  models_to_try = [primary_model] + [
      m for m in available_models if m != primary_model
  ]

  for i in range(0, total_blocks, chunk_size):
    chunk_blocks = blocks[i : i + chunk_size]
    chunk_text = "\n\n".join(chunk_blocks)

    progress_percent = min(1.0, (i + chunk_size) / total_blocks)
    status_text.text(
        f"Gemini ဖြင့် ဘာသာပြန်နေစဉ်... အပိုင်း ({i+1} မှ"
        f" {min(i+1+chunk_size, total_blocks)} / {total_blocks} စာကြောင်းများ)"
    )
    progress_bar.progress(progress_percent)

    # 🚀 ပိုမိုမြန်ဆန်ပြီး ရှင်းလင်းသော Prompt (Latency ကို လျှော့ချရန်)
    prompt = f"""You are a professional subtitle translator. Translate the following SRT into natural, fluent Burmese.

RULES:
1. Keep SRT structure, sequence numbers, and timecodes exact. Translate text only.
2. Use ONLY Burmese script. Do NOT mix with Bengali, Hindi, or other foreign scripts.
3. Integrate brief technical notes inside square brackets [...] into the nearest suitable subtitle line.
4. Keep the style natural for video subtitles.

SRT Content:
{chunk_text}"""

    chunk_success = False
    last_err = ""

    for model_name in models_to_try:
      url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key.strip()}"
      headers = {"Content-Type": "application/json"}
      payload = {"contents": [{"parts": [{"text": prompt}]}]}

      max_retries = 3
      for attempt in range(max_retries):
        try:
          response = requests.post(url, headers=headers, json=payload, timeout=60)
          res_json = response.json()

          if response.status_code == 200:
            translated_chunk = (
                res_json["candidates"][0]["content"]["parts"][0]["text"]
                .strip()
            )
            translated_blocks.append(translated_chunk)
            chunk_success = True
            break

          err_msg = (
              res_json.get("error", {}).get("message", "Unknown Error")
          )
          last_err = err_msg

          if any(
              kw in err_msg.lower()
              for kw in [
                  "high demand",
                  "resource_exhausted",
                  "quota",
                  "503",
                  "429",
                  "temporary",
              ]
          ):
            if attempt < max_retries - 1:
              wait_sec = (attempt + 1) * 2
              time.sleep(wait_sec)
              continue
          break
        except Exception as e:
          last_err = str(e)
          time.sleep(1)

        if chunk_success:
          break

      if not chunk_success:
        raise Exception(
            f"Gemini API Chunk Error at block {i+1}: {last_err}"
        )

  progress_bar.empty()
  status_text.empty()
  return "\n\n".join(translated_blocks) + "\n\n"


# ရရှိနိုင်သော Models များကို အလိုအလျောက် လှမ်းယူခြင်း
available_models = []
try:
  list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY.strip()}"
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
  selected_model = st.sidebar.selectbox(
      "🤖 Gemini Model ကို ရွေးပါ", available_models
  )

uploaded_file = st.file_uploader(
    "ဗီဒီယို သို့မဟုတ် အသံဖိုင် တင်ပါ (mp3, wav, mp4, m4a)",
    type=["mp3", "wav", "mp4", "m4a"],
)

if uploaded_file:
  if not selected_model:
    st.warning("⚠️ ကျေးဇူးပြု၍ Gemini API Key နှင့် Model ကို စစ်ဆေးပါ။")
  else:
    if st.button("🚀 Subtitle ထုတ်ပြီး Gemini ဖြင့် မြန်ဆန်စွာ ဘာသာပြန်မည်"):
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
          st.info("🎙️ Groq Whisper ဖြင့် အသံများကို စာသားအဖြစ် ပြောင်းလဲနေပါသည်...")
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
          raw_srt = json_to_srt(segments)

          # ၂။ Gemini ဖြင့် မြန်ဆန်သော Prompt ဖြင့် အပိုင်းလိုက် ဘာသာပြန်ခြင်း (chunk_size = 10 တိုင်း ထားရှိသည်)
          translated_srt = translate_srt_with_gemini_chunks(
              GEMINI_API_KEY,
              raw_srt,
              selected_model,
              available_models,
              chunk_size=10,
          )

          st.success("🎉 ဘာသာပြန်ခြင်း အောင်မြင်ပါသည်!")

          st.download_button(
              label="📥 မြန်မာ Subtitle (.srt) ဒေါင်းလုဒ်ဆွဲရန်",
              data=translated_srt,
              file_name="burmese_subtitles.srt",
              mime="text/plain",
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
