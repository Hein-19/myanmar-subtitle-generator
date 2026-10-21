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

st.title("🎬 Myanmar Subtitle Studio (Chunk Size 25)")
st.caption("Groq Whisper + Gemini Multi-Model Translation")

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


def translate_srt_with_gemini(
    api_key, raw_srt, model_name="gemini-2.5-flash", chunk_size=25
):
  blocks = [b.strip() for b in raw_srt.strip().split("\n\n") if b.strip()]
  translated_blocks = []
  total_blocks = len(blocks)

  progress_bar = st.progress(0)
  status_placeholder = st.empty()

  url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key.strip()}"
  headers = {"Content-Type": "application/json"}

  for i in range(0, total_blocks, chunk_size):
    chunk_blocks = blocks[i : i + chunk_size]
    chunk_text = "\n\n".join(chunk_blocks)

    start_block = i + 1
    end_block = min(i + chunk_size, total_blocks)

    progress_bar.progress(min(1.0, (i + chunk_size) / total_blocks))
    status_placeholder.info(
        f"🇲🇲 Gemini ({model_name}) ဖြင့် ဘာသာပြန်နေစဉ်... ({start_block} မှ"
        f" {end_block} / {total_blocks} စာကြောင်းများ)"
    )

    prompt = f"""You are an elite subtitle translator specializing in Japanese anime, movies, and conversational dialogue.
Translate the following SRT subtitles (Japanese Kanji/Kana or English) into fluent, natural, and expressive Burmese (Myanmar language).

TRANSLATION GUIDELINES:
1. Do NOT translate word-by-word literally. Capture the true emotion, tone, politeness level, and context suitable for anime/movie subtitles.
2. Maintain the exact same SRT sequence numbers and timestamps.
3. Only translate the dialogue text lines into Burmese.
4. If a line is too long, wrap it into two balanced lines using a single newline (\\n).
5. Output pure SRT only without markdown formatting, code ticks (```), or introductory notes.

SRT Content:
{chunk_text}"""

    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    chunk_success = False
    while not chunk_success:
      try:
        response = requests.post(
            url, headers=headers, json=payload, timeout=60
        )
        res_json = response.json()

        if response.status_code == 200:
          translated_chunk = res_json["candidates"][0]["content"]["parts"][0][
              "text"
          ].strip()
          if translated_chunk.startswith("```"):
            lines = translated_chunk.split("\n")
            translated_chunk = "\n".join(
                [line for line in lines if not line.strip().startswith("```")]
            ).strip()

          translated_blocks.append(translated_chunk)
          chunk_success = True
          time.sleep(4)
          break

        err_msg = str(res_json.get("error", {})).lower()
        if (
            "429" in err_msg
            or "quota" in err_msg
            or "resource_exhausted" in err_msg
        ):
          for sec in range(60, 0, -1):
            status_placeholder.warning(
                f"⏳ Gemini Rate Limit ခေတ္တပြည့်သွားသဖြင့် စက္ကန့် {sec}"
                f" စောင့်ဆိုင်းနေပါသည်... စက္ကန့်ပြည့်ပါက အပိုင်း ({start_block})"
                " မှ ဆက်လက် ဘာသာပြန်ပါမည်။"
            )
            time.sleep(1)
        else:
          time.sleep(3)

      except Exception:
        time.sleep(3)

  progress_bar.empty()
  status_placeholder.empty()
  return "\n\n".join(translated_blocks) + "\n\n"


GROQ_API_KEY = st.secrets.get("GROQ_API_KEY", "")
SECRET_GEMINI_KEY = st.secrets.get("GEMINI_API_KEY", "")

if not GROQ_API_KEY:
  st.error(
      "⚠️ Streamlit Secrets ထဲတွင် GROQ_API_KEY မတွေ့ရှိပါ။"
      " .streamlit/secrets.toml ကို စစ်ဆေးပါ။"
  )
  st.stop()

# Sidebar
st.sidebar.header("🌐 မူရင်း ဘာသာစကား")
source_lang = st.sidebar.selectbox(
    "ဗီဒီယိုထဲက စကားပြော:",
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
st.sidebar.header("🔑 ဘာသာပြန်စနစ်")
input_gemini_key = st.sidebar.text_input(
    "Gemini API Key:", value=SECRET_GEMINI_KEY, type="password"
)
ACTIVE_GEMINI_KEY = input_gemini_key.strip() if input_gemini_key else ""

gemini_models = [
    "gemini-2.5-flash",
    "gemini-1.5-flash",
    "gemini-3-flash",
    "gemini-3.5-flash-lite",
]
selected_model = st.sidebar.selectbox(
    "🤖 Gemini Model ရွေးပါ:", gemini_models, index=0
)

tab1, tab2 = st.tabs([
    "🎙️ ၁။ ဗီဒီယိုမှ မူရင်း SRT ထုတ်ယူခြင်း",
    "🇲🇲 ၂။ SRT တင်ပြီး မြန်မာပြန်ဆိုခြင်း (၂၅ ကြောင်းစီ)",
])

with tab1:
  st.write(f"မူရင်း ဘာသာစကား - **{source_lang.upper()}** (Temperature=0.0)")
  uploaded_media = st.file_uploader(
      "ဗီဒီယို/အသံဖိုင် တင်ပါ",
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

        groq_client = Groq(api_key=GROQ_API_KEY.strip())
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
  st.write(
      "ဂျပန် SRT ဖိုင်ကို တင်ပါက Gemini က **တစ်ကြိမ်လျှင် ၂၅ ကြောင်းစီ**"
      " အစုလိုက် အမြန် ဘာသာပြန်ပေးပါမည်။"
  )
  uploaded_srt = st.file_uploader(
      "SRT ဖိုင် တင်ပါ (.srt)", type=["srt"], key="srt_uploader"
  )

  if uploaded_srt:
    srt_text = uploaded_srt.read().decode("utf-8", errors="ignore")

    if not ACTIVE_GEMINI_KEY:
      st.warning("⚠️ Gemini API Key ထည့်သွင်းပေးပါ။")
    else:
      if st.button("🚀 Gemini ဖြင့် မြန်မာပြန်ဆိုမည်", key="btn_run_translate"):
        with st.spinner("Gemini ဖြင့် စာတန်းထိုးများကို ဘာသာပြန်နေပါသည်..."):
          st.session_state.trans_srt = translate_srt_with_gemini(
              ACTIVE_GEMINI_KEY,
              srt_text,
              model_name=selected_model,
              chunk_size=25,  # ၂၅ ကြောင်းစီ အသေသတ်မှတ်ထားပါသည်
          )

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
