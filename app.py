from datetime import timedelta
import os
import subprocess
import tempfile
import time
from groq import Groq
import requests
import streamlit as st

st.set_page_config(
    page_title="Myanmar Subtitle AI Hub", page_icon="🎬", layout="centered"
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

st.title("🎬 Myanmar Subtitle Studio")
st.caption(
    "Groq Whisper (အသံဖမ်းယူမှု) + Google Gemini (သဘာဝကျသော မြန်မာဘာသာပြန်)"
)

# 🧠 Session State စနစ် (Tab တစ်ခုချင်းစီအတွက် သီးခြားမှတ်ဉာဏ်)
if "tab1_raw_srt" not in st.session_state:
  st.session_state.tab1_raw_srt = None
if "tab1_trans_srt" not in st.session_state:
  st.session_state.tab1_trans_srt = None
if "tab2_raw_srt" not in st.session_state:
  st.session_state.tab2_raw_srt = None
if "tab2_trans_srt" not in st.session_state:
  st.session_state.tab2_trans_srt = None


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


# Gemini ဖြင့် သဘာဝကျကျ ဘာသာပြန်မည့် စနစ် (Auto-Retry + Pacing ပါဝင်သည်)
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
      progress_percent = min(1.0, (i + chunk_size) / total_blocks)
      progress_bar.progress(progress_percent)
      status_placeholder.info(
          f"🇲🇲 Gemini ({model_name}) ဖြင့် ဘာသာပြန်နေစဉ်... အပိုင်း"
          f" ({start_block} မှ {end_block} / {total_blocks} စာကြောင်းများ)"
      )

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
          time.sleep(3.5)  # 15 RPM မကျော်စေရန် ပုံမှန် ၃.၅ စက္ကန့် အနားပေးခြင်း
          break

        err_msg = str(res_json.get("error", {})).lower()
        if (
            "429" in err_msg
            or "quota" in err_msg
            or "resource_exhausted" in err_msg
        ):
          for sec in range(60, 0, -1):
            status_placeholder.warning(
                f"⏳ Gemini Rate Limit ပြည့်သွားသဖြင့် စက္ကန့် {sec}"
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


# 🔒 Secrets မှ Keys များ ရယူခြင်း
try:
  GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
  GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except Exception:
  st.error(
      "⚠️ Streamlit Secrets ထဲတွင် API Keys များ ရှာမတွေ့ပါ။"
      " .streamlit/secrets.toml ကို စစ်ဆေးပါ။"
  )
  st.stop()

# Sidebar တွင် Gemini Model ရွေးချယ်မှု
available_models = [
    "gemini-2.5-flash",
    "gemini-1.5-flash",
    "gemini-3-flash",
    "gemini-3.5-flash-lite",
]
selected_model = st.sidebar.selectbox(
    "🤖 Gemini Translation Model", available_models, index=0
)

# 📑 Tab (၂) ခု ခွဲခြားခြင်း
main_tab1, main_tab2 = st.tabs([
    "🎥 Video/Audio မှ တိုက်ရိုက်ထုတ်မည်",
    "📄 ရှိပြီးသား SRT ဖိုင် တင်ပြီး Gemini ဖြင့် ဘာသာပြန်မည်",
])

# ================= TAB 1: VIDEO/AUDIO PIPELINE =================
with main_tab1:
  uploaded_file = st.file_uploader(
      "ဗီဒီယို သို့မဟုတ် အသံဖိုင် တင်ပါ",
      type=["mp3", "wav", "mp4", "m4a"],
      key="uploader_tab1",
  )

  if (
      uploaded_file
      and st.button(
          "🚀 Whisper ဖြင့် ဖမ်းပြီး Gemini ဖြင့် ဘာသာပြန်မည်",
          key="btn_tab1_run",
      )
  ):
    with st.spinner("ဖိုင်ကို လုပ်ဆောင်နေပါသည်..."):
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
          compressed_audio_path = tmp_file_path + "_comp.mp3"
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
        st.session_state.tab1_raw_srt = json_to_srt(segments)

        st.session_state.tab1_trans_srt = translate_srt_with_gemini(
            GEMINI_API_KEY,
            st.session_state.tab1_raw_srt,
            model_name=selected_model,
            chunk_size=15,
        )

      except Exception as e:
        st.error(f"Error ဖြစ်ပွားပါသည်: {str(e)}")
      finally:
        if os.path.exists(tmp_file_path):
          os.remove(tmp_file_path)
        if compressed_audio_path and os.path.exists(compressed_audio_path):
          os.remove(compressed_audio_path)

  if st.session_state.tab1_raw_srt and st.session_state.tab1_trans_srt:
    st.success("🎉 ဘာသာပြန်ခြင်း အောင်မြင်ပါသည်!")
    col1, col2 = st.columns(2)
    with col1:
      st.download_button(
          "📥 မူရင်း SRT (.srt) ဒေါင်းလုဒ်",
          st.session_state.tab1_raw_srt,
          file_name="original_subtitles.srt",
          key="dl_tab1_raw",
      )
    with col2:
      st.download_button(
          "📥 မြန်မာ SRT (.srt) ဒေါင်းလုဒ်",
          st.session_state.tab1_trans_srt,
          file_name="burmese_subtitles.srt",
          key="dl_tab1_trans",
      )

# ================= TAB 2: SRT UPLOAD & TRANSLATE =================
with main_tab2:
  st.write(
      "Groq မှ ရရှိလာသော မူရင်း English `.srt` ဖိုင်ကို တင်ပေးလိုက်ရုံဖြင့်"
      " Gemini က စကားပြော သဘာဝကျသော မြန်မာစာတန်းထိုးအဖြစ် ပြန်ဆိုပေးပါမည်။"
  )

  uploaded_srt = st.file_uploader(
      "English SRT ဖိုင်ကို တင်ပါ (.srt)", type=["srt"], key="uploader_tab2"
  )

  if uploaded_srt:
    srt_content = uploaded_srt.read().decode("utf-8", errors="ignore")
    st.session_state.tab2_raw_srt = srt_content

    if st.button("🚀 Gemini ဖြင့် မြန်မာဘာသာသို့ ပြန်ဆိုမည်", key="btn_tab2_run"):
      with st.spinner("Gemini ဖြင့် စာတန်းထိုးများကို ဘာသာပြန်နေပါသည်..."):
        st.session_state.tab2_trans_srt = translate_srt_with_gemini(
            GEMINI_API_KEY,
            st.session_state.tab2_raw_srt,
            model_name=selected_model,
            chunk_size=15,
        )

  if st.session_state.tab2_trans_srt:
    st.success("🎉 မြန်မာစာတန်းထိုး အောင်မြင်စွာ ထွက်ရှိပါပြီ!")
    st.download_button(
        "📥 မြန်မာ SRT (.srt) ဒေါင်းလုဒ်",
        st.session_state.tab2_trans_srt,
        file_name="burmese_subtitles.srt",
        key="dl_tab2_trans",
    )

    with st.expander("မြန်မာဘာသာပြန် စာသားများ အစမ်းကြည့်ရှုရန်", expanded=True):
      st.text_area(
          "Burmese Output",
          st.session_state.tab2_trans_srt,
          height=300,
          key="tab2_preview",
      )
