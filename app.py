import streamlit as st
from groq import Groq
import tempfile
import os
import subprocess
from datetime import timedelta

st.set_page_config(page_title="Myanmar Subtitle AI", page_icon="🎬", layout="centered")

st.markdown("""
    
""", unsafe_allow_html=True)

st.title("🎬 Myanmar Subtitle Generator & Translator")
st.write("Groq AI (Whisper + LLaMA 3) သုံးပြီး Subtitle (.srt) အပိုင်းလိုက် ခွဲထုတ် ဘာသာပြန်မည်")

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

# SRT ကို အပိုင်းလိုက်ခွဲပြီး ဘာသာပြန်သည့် Function (Chunking Translation)
def translate_srt_in_chunks(groq_client, raw_srt, chunk_size=25):
    blocks = [b.strip() for b in raw_srt.strip().split("\n\n") if b.strip()]
    translated_blocks = []
    
    total_blocks = len(blocks)
    progress_bar = st.progress(0)
    status_text = st.empty()

    for i in range(0, total_blocks, chunk_size):
        chunk_blocks = blocks[i:i + chunk_size]
        chunk_text = "\n\n".join(chunk_blocks)
        
        progress_percent = min(1.0, (i + chunk_size) / total_blocks)
        status_text.text(f"ဘာသာပြန်နေစဉ်... အပိုင်း ({i+1} မှ {min(i+1+chunk_size, total_blocks)} / {total_blocks} စာကြောင်းများ)")
        progress_bar.progress(progress_percent)

        prompt = f"""You are a professional subtitle translator. 
Translate the following SRT content into natural and fluent Burmese (Myanmar language).

STRICT RULES:
1. Keep the SRT structure, sequence numbers, and timecodes EXACTLY the same.
2. Only translate the text lines, do not alter timestamps.
3. Use natural spoken Burmese suitable for movie subtitles.

SRT Content:
{chunk_text}"""

        try:
            response = groq_client.chat.completions.create(
                model="llama-3.1-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            translated_chunk = response.choices[0].message.content.strip()
            translated_blocks.append(translated_chunk)
        except Exception as e:
            raise Exception(f"Translation Chunk Error: {str(e)}")

    progress_bar.empty()
    status_text.empty()
    return "\n\n".join(translated_blocks) + "\n\n"

# Sidebar - API Key
st.sidebar.header("🔑 API Key")
groq_api_key = st.sidebar.text_input("Groq API Key", type="password")

uploaded_file = st.file_uploader("ဗီဒီယို သို့မဟုတ် အသံဖိုင် တင်ပါ (mp3, wav, mp4, m4a)", type=["mp3", "wav", "mp4", "m4a"])

if uploaded_file:
    if not groq_api_key:
        st.warning("⚠️ ကျေးဇူးပြု၍ ဘယ်ဘက် Sidebar တွင် Groq API Key ဖြည့်သွင်းပါ။")
    else:
        if st.button("🚀 Subtitle ထုတ်ပြီး အပိုင်းလိုက် ဘာသာပြန်မည်"):
            with st.spinner("အသံဖိုင်ကို စစ်ဆေးနေပါသည်..."):
                
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

                    groq_client = Groq(api_key=groq_api_key.strip())

                    # ၁။ Whisper API ဖြင့် Subtitle ထုတ်ယူခြင်း
                    st.info("🎙️ Groq Whisper ဖြင့် အသံများကို စာသားအဖြစ် ပြောင်းလဲနေပါသည်...")
                    with open(audio_path, "rb") as file:
                        transcription = groq_client.audio.transcriptions.create(
                            file=(audio_path, file.read()),
                            model="whisper-large-v3",
                            response_format="verbose_json"
                        )
                    segments = transcription.segments if hasattr(transcription, 'segments') else transcription.get('segments', [])
                    raw_srt = json_to_srt(segments)

                    # ၂။ LLaMA 3 ဖြင့် အပိုင်းလိုက် (Chunking) ဘာသာပြန်ခြင်း
                    translated_srt = translate_srt_in_chunks(groq_client, raw_srt, chunk_size=25)

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
