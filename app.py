from datetime import timedelta
import os
import subprocess
import tempfile
import time
from groq import Groq
import requests
import streamlit as st

st.set_page_config(
    page_title="Myanmar Subtitle Studio", page_icon="🎬", layout="centered"
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
        height: 3em;
    }
    </style>
""",
    unsafe_allow_html=True,
)

st.title("🎬 Subtitle Studio (Groq + Gemini)")
st.caption(
    "Groq Whisper (မူရင်းအသံဖမ်းယူမှု) နှင့် Gemini AI (မြန်မာဘာသာပြန်)"
)

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


def translate_srt_with_gemini(
    api_key, raw_srt, model_name="gemini-2.5-flash", chunk_size=15
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
        f" {end_block} / {total_blocks})"
    )

    prompt = f"""You are a professional subtitle translator.
Translate the following English SRT into natural, fluent, and conversational Burmese (Myanmar language) suitable for movies.
Do NOT translate word-by-word literally. Translate the natural conversational meaning.

STRICT RULES:
1. Keep the exact SRT numbering and timestamps intact.
2. Only translate the text lines into natural spoken Burmese.
3. If a sentence is long, wrap it into two lines using a single newline (\\n).
4. Output pure SRT only without extra introductory words or markdown notes.

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
          translated_blocks.append(translated_chunk)
          chunk_success = True
          time.sleep(3.5)
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


# 🔒 Secrets မှ GROQ_API_KEY ကိုသာ မဖြစ်မနေ စစ်ဆေးခြင်း
GROQ_API_KEY = st.secrets.get("GROQ_API_KEY", "")
SECRET_GEMINI_KEY = st.secrets.get("GEMINI_API_KEY", "")

if not GROQ_API_KEY:
  st.error(
      "⚠️ Streamlit Secrets ထဲတွင် GROQ_API_KEY မတွေ့ရှိပါ။"
      " .streamlit/secrets.toml ကို စစ်ဆေးပါ။"
  )
  st.stop()

# ⚙️ Sidebar Settings (Gemini Key မရှိလည်း ပြဿနာမရှိစေရန် ပြင်ဆင်ထားသည်)
st.sidebar.header("⚙️ API Configuration")
input_gemini_key = st.sidebar.text_input(
    "🔑 Gemini API Key (ရွေးချယ်နိုင်သည်)",
    value=SECRET_GEMINI_KEY,
    type="password",
    help=(
        "Gemini Key ထည့်မထားပါက Groq ဖြင့် မူရင်း English SRT ကိုသာ ထုတ်ယူနိုင်ပါမည်။"
    ),
)
ACTIVE_GEMINI_KEY = input_gemini_key.strip() if input_gemini_key else ""

available_gemini_models = [
    "gemini-2.5-flash",
    "gemini-1.5-flash",
    "gemini-3-flash",
    "gemini-3.5-flash-lite",
]
selected_model = st.sidebar.selectbox(
    "🤖 Gemini Model", available_gemini_models, index=0
)

# 📑 Tabs ခွဲခြားခြင်း
tab1, tab2 = st.tabs([
    "🎙️ ၁။ ဗီဒီယိုမှ မူရင်း SRT ထုတ်ယူခြင်း (Groq)",
    "🇲🇲 ၂။ SRT တင်ပြီး မြန်မာပြန်ဆိုခြင်း (Gemini)",
])

# ================= TAB 1: GROQ WHISPER =================
with tab1:
  st.write(
      "ဗီဒီယို သို့မဟုတ် အသံဖိုင်ကို တင်ပါက **Groq Whisper** ဖြင့်"
      " အင်္ဂလိပ်စာတန်းထိုး (.srt) အမြန်ဖမ်းယူ ထုတ်ပေးပါမည်။"
  )

  uploaded_media = st.file_uploader(
      "ဗီဒီယို သို့မဟုတ် အသံဖိုင် တင်ပါ",
      type=["mp3", "wav", "mp4", "m4a"],
      key="media_uploader",
  )

  if uploaded_media and st.button(
      "🚀 Groq Whisper ဖြင့် မူရင်း SRT ထုတ်မည်", key="btn_run_whisper"
  ):
    with st.spinner("ဖိုင်ကို Processing လုပ်နေပါသည်..."):
      file_ext = os.path.splitext(uploaded_media.name)[1].lower()
      with tempfile.NamedTemporaryFile(
          delete=False, suffix=file_ext
      ) as tmp_file:
        tmp_file.write(uploaded_media.read())
        tmp_file_path = tmp_file.name

      audio_path = tmp_file_path
      compressed_audio_path = None

      try:
        # ၂၄ MB ထက်ကြီးပါက ချုံ့ခြင်း
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
        groq_client = Groq(api_key=GROQ_API_KEY.strip())
        with open(audio_path, "rb") as f:
          transcription = groq_client.audio.transcriptions.create(
              file=(audio_path, f.read()),
              model="whisper-large-v3",
              response_format="verbose_json",
          )

        segments = (
            transcription.segments
            if hasattr(transcription, "segments")
            else transcription.get("segments", [])
        )
        st.session_state.raw_srt = json_to_srt(segments)
        st.success("🎉 မူရင်း SRT စာတန်းထိုး ထုတ်ယူပြီးပါပြီ!")

      except Exception as e:
        st.error(f"Error ဖြစ်ပွားပါသည်: {str(e)}")
      finally:
        if os.path.exists(tmp_file_path):
          os.remove(tmp_file_path)
        if compressed_audio_path and os.path.exists(compressed_audio_path):
          os.remove(compressed_audio_path)

  if st.session_state.raw_srt:
    st.download_button(
        label="📥 မူရင်း English SRT (.srt) ဒေါင်းလုဒ်",
        data=st.session_state.raw_srt,
        file_name="original_subtitles.srt",
        mime="text/plain",
        key="btn_dl_raw_tab1",
    )
    with st.expander("မူရင်း စာတန်းထိုးများ ကြည့်ရှုရန်"):
      st.text_area(
          "Original SRT Output",
          st.session_state.raw_srt,
          height=250,
          key="preview_raw",
      )

# ================= TAB 2: GEMINI TRANSLATOR =================
with tab2:
  st.write("ရရှိလာသော SRT ဖိုင်ကို တင်ပြီး Gemini ဖြင့် မြန်မာဘာသာ ပြန်ဆိုနိုင်ပါသည်။")

  uploaded_srt = st.file_uploader(
      "English SRT ဖိုင်ကို တင်ပါ (.srt)", type=["srt"], key="srt_uploader"
  )

  if uploaded_srt:
    srt_text = uploaded_srt.read().decode("utf-8", errors="ignore")

    if not ACTIVE_GEMINI_KEY:
      st.warning(
          "⚠️ Gemini API Key မရှိသေးပါ။ ဘယ်ဘက် Sidebar တွင် Gemini Key"
          " ထည့်သွင်းပေးပါ။ (သို့မဟုတ် အဆိုပါ SRT ဖိုင်ကို Chat ထဲသို့ ပို့၍"
          " ဘာသာပြန်ခိုင်းနိုင်ပါသည်)"
      )
    else:
      if st.button("🚀 Gemini ဖြင့် မြန်မာပြန်ဆိုမည်", key="btn_run_translate"):
        with st.spinner("Gemini ဖြင့် စာတန်းထိုးများကို ဘာသာပြန်နေပါသည်..."):
          st.session_state.trans_srt = translate_srt_with_gemini(
              ACTIVE_GEMINI_KEY,
              srt_text,
              model_name=selected_model,
              chunk_size=15,
          )

  if st.session_state.trans_srt:
    st.success("🎉 မြန်မာစာတန်းထိုး အောင်မြင်စွာ ရရှိပါပြီ!")
    st.download_button(
        label="📥 မြန်မာ SRT (.srt) ဒေါင်းလုဒ်",
        data=st.session_state.trans_srt,
        file_name="burmese_subtitles.srt",
        mime="text/plain",
        key="btn_dl_trans_tab2",
    )
    with st.expander("မြန်မာစာတန်းထိုး ကြည့်ရှုရန်", expanded=True):
      st.text_area(
          "Translated Burmese SRT",
          st.session_state.trans_srt,
          height=250,
          key="preview_trans",
      )
