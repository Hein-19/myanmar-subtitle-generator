from datetime import timedelta
import os
import subprocess
import tempfile
import time
from groq import Groq
import streamlit as st

st.set_page_config(
    page_title="Myanmar Subtitle AI (Groq Pipeline)",
    page_icon="🎬",
    layout="centered",
)

# Custom Styling
st.markdown(
    """
    <style>
    .stButton>button {
        width: 100%;
        background-color: #f55036;
        color: white;
        font-weight: bold;
        border-radius: 8px;
        height: 3em;
    }
    </style>
""",
    unsafe_allow_html=True,
)

st.title("⚡ Groq Full Subtitle Generator")
st.caption(
    "Groq Whisper-Large-v3 (အသံဖမ်းယူမှု) + Groq Llama 3 (မြန်မာဘာသာပြန်)"
)

# 🧠 Session State စနစ် (Download နှိပ်လျှင် ပျောက်မသွားစေရန်)
if "raw_srt" not in st.session_state:
  st.session_state.raw_srt = None
if "translated_srt" not in st.session_state:
  st.session_state.translated_srt = None


# Timestamp ပြောင်းလဲပေးသည့် function
def format_timestamp(seconds):
  td = timedelta(seconds=seconds)
  total_seconds = int(td.total_seconds())
  hours = total_seconds // 3600
  minutes = (total_seconds % 3600) // 60
  secs = total_seconds % 60
  millisecs = int((td.total_seconds() - total_seconds) * 1000)
  return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"


# Whisper segments မှ SRT စာသားအဖြစ် ပြောင်းလဲခြင်း
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


# Groq ဖြင့် မြန်မာဘာသာသို့ အမြန်ဘာသာပြန်မည့် Function (Fallback Models ပါဝင်သည်)
def translate_srt_with_groq(groq_client, raw_srt, chunk_size=20):
  blocks = [b.strip() for b in raw_srt.strip().split("\n\n") if b.strip()]
  translated_blocks = []

  total_blocks = len(blocks)
  progress_bar = st.progress(0)
  status_placeholder = st.empty()

  # စမ်းသပ်မည့် Groq Models များ (404 Error ကာကွယ်ရန်)
  candidate_models = [
      "llama-3.1-8b-instant",  # အမြန်ဆုံးနှင့် အငြိမ်ဆုံး Model
      "llama-3.3-70b-versatile",
      "llama3-70b-8192",
      "mixtral-8x7b-32768",
  ]

  system_prompt = """You are a professional Burmese subtitle translator.
Translate the following SRT subtitles into natural, conversational Burmese (Myanmar language).

STRICT RULES:
1. Maintain the exact same SRT sequence numbers and timestamps.
2. Only translate the subtitle text lines into Burmese.
3. If a sentence is long, wrap it into two lines using a newline (\\n).
4. Do not output any notes, introductory phrases, or markdown explanations. Output pure SRT only."""

  for i in range(0, total_blocks, chunk_size):
    chunk_blocks = blocks[i : i + chunk_size]
    chunk_text = "\n\n".join(chunk_blocks)

    start_block = i + 1
    end_block = min(i + chunk_size, total_blocks)

    progress_percent = min(1.0, (i + chunk_size) / total_blocks)
    progress_bar.progress(progress_percent)
    status_placeholder.info(
        f"⚡ Groq ဖြင့် ဘာသာပြန်နေစဉ်... အပိုင်း ({start_block} မှ"
        f" {end_block} / {total_blocks} စာကြောင်းများ)"
    )

    chunk_success = False

    for model_name in candidate_models:
      try:
        response = groq_client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": chunk_text},
            ],
            temperature=0.3,
        )

        translated_chunk = response.choices[0].message.content.strip()
        translated_blocks.append(translated_chunk)
        chunk_success = True
        time.sleep(0.4)
        break

      except Exception as e:
        err_msg = str(e).lower()
        # 404 (Model not found) ဖြစ်ပါက နောက် model တစ်ခုသို့ အလိုအလျောက် ခုန်ကူးမည်
        if "404" in err_msg or "not found" in err_msg:
          continue
        else:
          time.sleep(2)

    if not chunk_success:
      translated_blocks.append(chunk_text)

  progress_bar.empty()
  status_placeholder.empty()
  return "\n\n".join(translated_blocks) + "\n\n"


# 🔒 Secrets မှ GROQ_API_KEY ခေါ်ယူခြင်း
try:
  GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
except Exception:
  st.error(
      "⚠️ Streamlit Secrets ထဲတွင် GROQ_API_KEY ကို ရှာမတွေ့ပါ။"
      " .streamlit/secrets.toml ကို စစ်ဆေးပါ။"
  )
  st.stop()

# ဖိုင်တင်ရန် နေရာ
uploaded_file = st.file_uploader(
    "ဗီဒီယို သို့မဟုတ် အသံဖိုင် တင်ပါ (mp3, wav, mp4, m4a)",
    type=["mp3", "wav", "mp4", "m4a"],
)

if uploaded_file:
  if not GROQ_API_KEY:
    st.warning("⚠️ ကျေးဇူးပြု၍ GROQ_API_KEY ထည့်သွင်းပါ။")
  else:
    if st.button("🚀 Groq ဖြင့် စာတန်းထိုး ထုတ်ပြီး မြန်မာပြန်မည်"):
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
          # ဖိုင်ဆိုဒ် 24MB ထက် ကြီးပါက ffmpeg ဖြင့် အသံဖိုင် အလိုအလျောက် ချုံ့ခြင်း
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

          groq_client = Groq(api_key=GROQ_API_KEY.strip())

          # ၁။ Groq Whisper ဖြင့် အသံဖမ်းယူခြင်း
          st.info("🎙️ Whisper-Large-v3 ဖြင့် အသံဖမ်းယူနေပါသည်...")
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

          # ၂။ Groq Llama ဖြင့် မြန်မာဘာသာသို့ ပြန်ဆိုခြင်း
          st.info("🇲🇲 မြန်မာဘာသာသို့ အမြန် ပြန်ဆိုနေပါသည်...")
          st.session_state.translated_srt = translate_srt_with_groq(
              groq_client, st.session_state.raw_srt, chunk_size=20
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
  st.success("🎉 အားလုံး အောင်မြင်စွာ ပြီးစီးပါပြီ!")

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

  with st.expander("စာတန်းထိုးများ အစမ်းကြည့်ရှုရန်"):
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
