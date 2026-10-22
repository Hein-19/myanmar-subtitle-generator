from datetime import timedelta
import os
import subprocess
import tempfile
import time
from groq import Groq
import requests
import streamlit as st

st.set_page_config(
    page_title="Myanmar Subtitle Studio Pro", page_icon="🎬", layout="centered"
)

st.markdown(
    """
    <style>
    .stButton>button {
        width: 100%;
        background-color: #e50914;
        color: white;
        font-weight: bold;
        border-radius: 8px;
        height: 3em;
    }
    </style>
""",
    unsafe_allow_html=True,
)

st.title("🎬 Myanmar Subtitle Studio Pro")
st.caption("Groq Whisper + Gemini / Groq Multi-Engine Translation")

# 🧠 Session State စနစ်
if "raw_srt" not in st.session_state:
  st.session_state.raw_srt = None
if "trans_srt" not in st.session_state:
  st.session_state.trans_srt = None


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


# 🌐 ဘာသာပြန် Core Function (Gemini ရော Groq ပါ ပံ့ပိုးသည်)
def translate_srt(
    engine, api_key, raw_srt, model_name, chunk_size=25, groq_client=None
):
  blocks = [b.strip() for b in raw_srt.strip().split("\n\n") if b.strip()]
  translated_blocks = []
  total_blocks = len(blocks)

  progress_bar = st.progress(0)
  status_placeholder = st.empty()

  system_prompt = """You are an elite subtitle translator specializing in Japanese anime, movies, and conversational dialogue.
Translate the following SRT subtitles into fluent, natural, and expressive Burmese (Myanmar language).

TRANSLATION GUIDELINES:
1. Do NOT translate word-by-word literally. Capture the true emotion, tone, politeness level, and context suitable for movie subtitles.
2. Maintain the exact same SRT sequence numbers and timestamps.
3. Only translate the dialogue text lines into Burmese.
4. If a line is too long, wrap it into two balanced lines using a single newline (\\n).
5. Output pure SRT only without markdown formatting, code ticks (```), or introductory notes."""

  for i in range(0, total_blocks, chunk_size):
    chunk_blocks = blocks[i : i + chunk_size]
    chunk_text = "\n\n".join(chunk_blocks)

    start_block = i + 1
    end_block = min(i + chunk_size, total_blocks)

    progress_bar.progress(min(1.0, (i + chunk_size) / total_blocks))
    status_placeholder.info(
        f"🇲🇲 {engine} ({model_name}) ဖြင့် ဘာသာပြန်နေစဉ်... ({start_block} မှ"
        f" {end_block} / {total_blocks} စာကြောင်းများ)"
    )

    chunk_success = False
    max_attempts = 5

    for attempt in range(max_attempts):
      try:
        if engine == "Google Gemini":
          url = f"[https://generativelanguage.googleapis.com/v1beta/models/](https://generativelanguage.googleapis.com/v1beta/models/){model_name}:generateContent?key={api_key.strip()}"
          headers = {"Content-Type": "application/json"}
          prompt = f"{system_prompt}\n\nSRT Content:\n{chunk_text}"
          payload = {"contents": [{"parts": [{"text": prompt}]}]}

          response = requests.post(
              url, headers=headers, json=payload, timeout=60
          )
          res_json = response.json()

          if response.status_code == 200:
            translated_chunk = res_json["candidates"][0]["content"]["parts"][0][
                "text"
            ].strip()
            chunk_success = True
            time.sleep(4)
          else:
            err_data = res_json.get("error", {})
            err_msg = str(err_data).lower()
            if (
                response.status_code == 429
                or "quota" in err_msg
                or "resource_exhausted" in err_msg
            ):
              for sec in range(60, 0, -1):
                status_placeholder.warning(
                    f"⏳ Gemini Rate Limit ခေတ္တစောင့်ဆိုင်းနေပါသည်... စက္ကန့်"
                    f" {sec}"
                )
                time.sleep(1)
            else:
              st.error(
                  f"❌ Gemini Error ({response.status_code}):"
                  f" {err_data.get('message', str(err_data))}"
              )
              progress_bar.empty()
              status_placeholder.empty()
              return None

        else:  # Groq AI (Free) Engine
          response = groq_client.chat.completions.create(
              model=model_name,
              messages=[
                  {"role": "system", "content": system_prompt},
                  {"role": "user", "content": chunk_text},
              ],
              temperature=0.3,
          )
          translated_chunk = response.choices[0].message.content.strip()
          chunk_success = True
          time.sleep(1.5)

        if chunk_success:
          if translated_chunk.startswith("```"):
            lines = translated_chunk.split("\n")
            translated_chunk = "\n".join(
                [line for line in lines if not line.strip().startswith("```")]
            ).strip()
          translated_blocks.append(translated_chunk)
          break

      except Exception as ex:
        time.sleep(3)

    if not chunk_success:
      st.error(
          f"❌ အပိုင်း ({start_block} မှ {end_block}) တွင် Error ဖြစ်သဖြင့်"
          " ရပ်တန့်သွားပါသည်။"
      )
      progress_bar.empty()
      status_placeholder.empty()
      return None

  progress_bar.empty()
  status_placeholder.empty()
  return "\n\n".join(translated_blocks) + "\n\n"


# 🔒 Secrets စစ်ဆေးခြင်း
GROQ_API_KEY = st.secrets.get("GROQ_API_KEY", "")
SECRET_GEMINI_KEY = st.secrets.get("GEMINI_API_KEY", "")

if not GROQ_API_KEY:
  st.error(
      "⚠️ Streamlit Secrets ထဲတွင် GROQ_API_KEY မတွေ့ရှိပါ။"
      " .streamlit/secrets.toml ကို စစ်ဆေးပါ။"
  )
  st.stop()

groq_client = Groq(api_key=GROQ_API_KEY.strip())

# ⚙️ SIDEBAR CONFIGURATIONS
st.sidebar.header("🌐 မူရင်း ဘာသာစကား သတ်မှတ်ခြင်း")
source_lang = st.sidebar.selectbox(
    "ဗီဒီယို/အသံဖိုင်ထဲက မူရင်းစကားပြော:",
    options=["ja", "en", "ko", "zh", "auto"],
    format_func=lambda x: {
        "ja": "🇯🇵 ဂျပန် (Japanese)",
        "en": "🇬🇧 အင်္ဂလိပ် (English)",
        "ko": "🇰🇷 ကိုရီးယား (Korean)",
        "zh": "🇨🇳 တရုတ် (Chinese)",
        "auto": "🌐 အလိုအလျောက် (Auto)",
    }.get(x, x),
    index=0,
)

st.sidebar.markdown("---")
st.sidebar.header("⚙️ ဘာသာပြန် Engine & Settings")

# ၁။ ဘာသာပြန်မည့် စနစ် ရွေးချယ်မှု
translation_engine = st.sidebar.radio(
    "ဘာသာပြန်မည့် စနစ်ကို ရွေးပါ:",
    ["Google Gemini", "Groq AI (Free)"],
    index=0,
)

# ၂။ Chunk Size Slider (Default 25)
selected_chunk_size = st.sidebar.slider(
    "📏 Chunk Size (တစ်ကြိမ်ပို့မည့် စာကြောင်းအရေအတွက်):",
    min_value=10,
    max_value=100,
    value=25,
    step=5,
)

# ၃။ Engine အလိုက် Models နှင့် Keys ခွဲခြားခြင်း
if translation_engine == "Google Gemini":
  input_gemini_key = st.sidebar.text_input(
      "Gemini API Key:",
      value=SECRET_GEMINI_KEY,
      type="password",
      help="Gemini Key ထည့်သွင်းပေးပါ (မရှိပါက Groq AI သို့ ပြောင်းပါ)။",
  )
  ACTIVE_GEMINI_KEY = input_gemini_key.strip() if input_gemini_key else ""

  gemini_models = [
      "gemini-2.5-flash",
      "gemini-1.5-flash",
      "gemini-2.5-pro",
      "gemini-1.5-pro",
      "gemini-3-flash",
      "gemini-3.5-flash-lite",
  ]
  selected_model = st.sidebar.selectbox(
      "🤖 Gemini Model ရွေးပါ:", gemini_models, index=0
  )
else:
  st.sidebar.info("💡 Groq Key ကို Secrets မှ အလိုအလျောက် အသုံးပြုပါမည်။")
  groq_models = [
      "qwen/qwen3.8-27b",
      "openai/gpt-oss-20b",
      "llama-3.3-70b-versatile",
      "llama-3.1-8b-instant",
      "openai/gpt-oss-120b",
  ]
  selected_model = st.sidebar.selectbox(
      "🤖 Groq Model ရွေးပါ:", groq_models, index=0
  )
  ACTIVE_GEMINI_KEY = ""

# 📑 Tabs
tab1, tab2 = st.tabs([
    "🎙️ ၁။ ဗီဒီယိုမှ မူရင်း SRT ထုတ်ယူခြင်း (Groq)",
    "🇲🇲 ၂။ SRT ဖိုင်တင်ပြီး မြန်မာပြန်ဆိုခြင်း",
])

# ================= TAB 1: GROQ WHISPER =================
with tab1:
  st.write(
      f"လက်ရှိ ဘာသာစကား - **{source_lang.upper()}** (Temperature=0.0 ဖြင့်"
      " အသံတိတ်ပိုင်း English အမှားများ မထွက်အောင် ဖမ်းယူပါမည်)"
  )

  uploaded_media = st.file_uploader(
      "ဗီဒီယို သို့မဟုတ် အသံဖိုင် တင်ပါ",
      type=["mp3", "wav", "mp4", "m4a"],
      key="media_uploader",
  )

  if uploaded_media and st.button(
      "🚀 Whisper ဖြင့် မူရင်း SRT ထုတ်မည်", key="btn_run_whisper"
  ):
    with st.spinner("ဖိုင်ကို လုပ်ဆောင်နေပါသည်..."):
      file_ext = os.path.splitext(uploaded_media.name)[1].lower()
      with tempfile.NamedTemporaryFile(
          delete=False, suffix=file_ext
      ) as tmp_file:
        tmp_file.write(uploaded_media.read())
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

        st.info("🎙️ Groq Whisper-Large-v3 ဖြင့် အသံဖမ်းယူနေပါသည်...")

        with open(audio_path, "rb") as audio_file:
          transcription_kwargs = {
              "file": (os.path.basename(audio_path), audio_file.read()),
              "model": "whisper-large-v3",
              "response_format": "verbose_json",
              "temperature": 0.0,
          }

          if source_lang == "ja":
            transcription_kwargs["language"] = "ja"
            transcription_kwargs["prompt"] = (
                "こんにちは。これは日本語のアニメ・会話の音声です。音楽や無音部分で英語を出力しないでください。"
            )
          elif source_lang != "auto":
            transcription_kwargs["language"] = source_lang

          transcription = groq_client.audio.transcriptions.create(
              **transcription_kwargs
          )

        segments = (
            transcription.segments
            if hasattr(transcription, "segments")
            else transcription.get("segments", [])
        )
        st.session_state.raw_srt = json_to_srt(segments)
        st.success("🎉 မူရင်း SRT စာတန်းထိုး အောင်မြင်စွာ ရရှိပါပြီ!")

      except Exception as e:
        st.error(f"Error ဖြစ်ပွားပါသည်: {str(e)}")
      finally:
        if os.path.exists(tmp_file_path):
          os.remove(tmp_file_path)
        if compressed_audio_path and os.path.exists(compressed_audio_path):
          os.remove(compressed_audio_path)

  if st.session_state.raw_srt:
    file_prefix = "japanese" if source_lang == "ja" else "original"
    st.download_button(
        label=f"📥 မူရင်း {source_lang.upper()} SRT (.srt) ဒေါင်းလုဒ်",
        data=st.session_state.raw_srt,
        file_name=f"{file_prefix}_subtitles.srt",
        mime="text/plain",
        key="btn_dl_raw_tab1",
    )
    with st.expander("မူရင်း စာတန်းထိုးများ အစမ်းကြည့်ရှုရန်", expanded=True):
      st.text_area(
          "Original Subtitles Output",
          st.session_state.raw_srt,
          height=250,
          key="preview_raw",
      )

# ================= TAB 2: TRANSLATOR =================
with tab2:
  st.write(
      f"လက်ရှိရွေးချယ်မှု - **{translation_engine}** | Model - **{selected_model}**"
      f" | Chunk Size - **{selected_chunk_size} ကြောင်းစီ**"
  )

  uploaded_srt = st.file_uploader(
      "SRT ဖိုင်ကို တင်ပါ (.srt)", type=["srt"], key="srt_uploader"
  )

  if uploaded_srt:
    srt_text = uploaded_srt.read().decode("utf-8", errors="ignore")

    if translation_engine == "Google Gemini" and not ACTIVE_GEMINI_KEY:
      st.warning(
          "⚠️ Gemini API Key မရှိသေးပါ။ Sidebar တွင် Gemini Key ထည့်ပါ"
          " (သို့မဟုတ် Engine ကို Groq AI (Free) သို့ ပြောင်းပါ)။"
      )
    else:
      if st.button("🚀 မြန်မာဘာသာသို့ ပြန်ဆိုမည်", key="btn_run_translate"):
        with st.spinner(f"{translation_engine} ဖြင့် ဘာသာပြန်နေပါသည်..."):
          result = translate_srt(
              engine=translation_engine,
              api_key=ACTIVE_GEMINI_KEY,
              raw_srt=srt_text,
              model_name=selected_model,
              chunk_size=selected_chunk_size,
              groq_client=groq_client,
          )
          if result:
            st.session_state.trans_srt = result

  if st.session_state.trans_srt:
    st.success("🎉 မြန်မာစာတန်းထိုး အောင်မြင်စွာ ရရှိပါပြီ!")
    st.download_button(
        label="📥 မြန်မာ SRT (.srt) ဒေါင်းလုဒ်",
        data=st.session_state.trans_srt,
        file_name="burmese_subtitles.srt",
        mime="text/plain",
        key="btn_dl_trans_tab2",
    )
    with st.expander("မြန်မာစာတန်းထိုး အစမ်းကြည့်ရှုရန်", expanded=True):
      st.text_area(
          "Translated Burmese SRT",
          st.session_state.trans_srt,
          height=250,
          key="preview_trans",
      )
