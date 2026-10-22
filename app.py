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

st.title("🎬 Myanmar Subtitle Studio (OpenRouter)")
st.caption("Groq Whisper + OpenRouter Free Models Translation")

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


def translate_srt_with_openrouter(
    api_key,
    raw_srt,
    model_name="minimax/minimax-m3.1-flash:free",
    chunk_size=25,
):
  blocks = [b.strip() for b in raw_srt.strip().split("\n\n") if b.strip()]
  translated_blocks = []
  total_blocks = len(blocks)

  progress_bar = st.progress(0)
  status_placeholder = st.empty()

  url = "https://openrouter.ai/api/v1/chat/completions"
  headers = {
      "Authorization": f"Bearer {api_key.strip()}",
      "Content-Type": "application/json",
  }

  system_prompt = """You are an elite subtitle translator specializing in Japanese anime, movies, and conversational dialogue.
Translate the following SRT subtitles into fluent, natural, and expressive Burmese (Myanmar language).

TRANSLATION GUIDELINES:
1. Do NOT translate word-by-word literally. Capture the true emotion, tone, and context.
2. Maintain the exact same SRT sequence numbers and timestamps.
3. Only translate the dialogue text lines into Burmese.
4. Output pure SRT only without markdown formatting or code ticks (```)."""

  for i in range(0, total_blocks, chunk_size):
    chunk_blocks = blocks[i : i + chunk_size]
    chunk_text = "\n\n".join(chunk_blocks)

    start_block = i + 1
    end_block = min(i + chunk_size, total_blocks)

    progress_bar.progress(min(1.0, (i + chunk_size) / total_blocks))
    status_placeholder.info(
        f"🇲🇲 OpenRouter ({model_name}) ဖြင့် ဘာသာပြန်နေစဉ်... ({start_block}"
        f" မှ {end_block} / {total_blocks} စာကြောင်းများ)"
    )

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"SRT Content:\n{chunk_text}",
            },
        ],
    }

    chunk_success = False
    for attempt in range(3):
      try:
        response = requests.post(
            url, headers=headers, json=payload, timeout=60
        )
        res_json = response.json()

        if response.status_code == 200:
          if "choices" in res_json and len(res_json["choices"]) > 0:
            translated_chunk = (
                res_json["choices"][0]["message"]["content"].strip()
            )
            if translated_chunk.startswith("```"):
              lines = translated_chunk.split("\n")
              translated_chunk = "\n".join([
                  line for line in lines if not line.strip().startswith("```")
              ]).strip()

            translated_blocks.append(translated_chunk)
            chunk_success = True
            time.sleep(2)
            break
          else:
            time.sleep(3)
        else:
          time.sleep(3)
      except Exception:
        time.sleep(3)

    if not chunk_success:
      st.error(
          f"❌ အပိုင်း ({start_block} မှ {end_block}) ကို ဘာသာပြန်ရာတွင်"
          " အမှားရှိနေပါသည်။"
      )
      progress_bar.empty()
      status_placeholder.empty()
      return None

  progress_bar.empty()
  status_placeholder.empty()
  return "\n\n".join(translated_blocks) + "\n\n"


GROQ_API_KEY = st.secrets.get("GROQ_API_KEY", "")

if not GROQ_API_KEY:
  st.error("⚠️ Streamlit Secrets ထဲတွင် GROQ_API_KEY မတွေ့ရှိပါ။")
  st.stop()

groq_client = Groq(api_key=GROQ_API_KEY.strip())

# Sidebar
st.sidebar.header("🌐 မူရင်း ဘာသာစကား")
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
st.sidebar.header("🔑 OpenRouter ဆက်တင်များ")
input_openrouter_key = st.sidebar.text_input(
    "OpenRouter API Key:", type="password"
)
ACTIVE_OPENROUTER_KEY = (
    input_openrouter_key.strip() if input_openrouter_key else ""
)

selected_chunk_size = st.sidebar.slider(
    "📏 Chunk Size (တစ်ကြိမ်ပို့မည့် စာကြောင်းရေ):",
    min_value=10,
    max_value=50,
    value=25,
    step=5,
)

openrouter_models = [
    "minimax/minimax-m3.1-flash:free",
    "recursive/flint:free",
]
selected_model = st.sidebar.selectbox(
    "🤖 OpenRouter Free Model ရွေးပါ:", openrouter_models, index=0
)

tab1, tab2 = st.tabs([
    "🎙️ ၁။ မူရင်း SRT ထုတ်ယူခြင်း (Groq)",
    "🇲🇲 ၂။ OpenRouter ဖြင့် မြန်မာပြန်ဆိုခြင်း",
])

with tab1:
  st.write(f"မူရင်း ဘာသာစကား - **{source_lang.upper()}** (Temperature=0.0)")
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
        st.success("🎉 မူရင်း SRT ရရှိပါပြီ!")

      except Exception as e:
        st.error(f"Error ဖြစ်ပွားပါသည်: {str(e)}")
      finally:
        if os.path.exists(tmp_file_path):
          os.remove(tmp_file_path)
        if compressed_audio_path and os.path.exists(compressed_audio_path):
          os.remove(compressed_audio_path)

  if st.session_state.raw_srt:
    st.download_button(
        "📥 မူရင်း SRT ဒေါင်းလုဒ်",
        data=st.session_state.raw_srt,
        file_name="original_subtitles.srt",
        key="btn_dl_raw_tab1",
    )

with tab2:
  st.write("OpenRouter Free မော်ဒယ်ဖြင့် စာတန်းထိုးများကို မြန်မာလို ဘာသာပြန်မည်။")
  uploaded_srt = st.file_uploader(
      "SRT ဖိုင် တင်ပါ (.srt)", type=["srt"], key="srt_uploader"
  )

  if uploaded_srt:
    srt_text = uploaded_srt.read().decode("utf-8", errors="ignore")
    if not ACTIVE_OPENROUTER_KEY:
      st.warning("⚠️ ဘယ်ဘက် Sidebar တွင် OpenRouter API Key ထည့်သွင်းပေးပါ။")
    else:
      if st.button("🚀 OpenRouter ဖြင့် မြန်မာပြန်ဆိုမည်", key="btn_run_translate"):
        with st.spinner("OpenRouter ဖြင့် ဘာသာပြန်နေပါသည်..."):
          result = translate_srt_with_openrouter(
              ACTIVE_OPENROUTER_KEY,
              srt_text,
              model_name=selected_model,
              chunk_size=selected_chunk_size,
          )
          if result:
            st.session_state.trans_srt = result

  if st.session_state.trans_srt:
    st.success("🎉 မြန်မာစာတန်းထိုး အောင်မြင်စွာ ရရှိပါပြီ!")
    st.download_button(
        "📥 မြန်မာ SRT (.srt) ဒေါင်းလုဒ်",
        data=st.session_state.trans_srt,
        file_name="burmese_subtitles.srt",
        key="btn_dl_trans_tab2",
    )
    with st.expander("မြန်မာစာတန်းထိုး အစမ်းကြည့်ရှုရန်", expanded=True):
      st.text_area(
          "Translated Burmese SRT",
          st.session_state.trans_srt,
          height=250,
          key="preview_trans",
      )
