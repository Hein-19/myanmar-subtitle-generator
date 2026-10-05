import streamlit as st
from groq import Groq
import google.generativeai as genai
import tempfile
import os
import subprocess
from datetime import timedelta

st.set_page_config(page_title="Myanmar Subtitle AI", page_icon="🎬", layout="centered")

st.markdown("""
    
""", unsafe_allow_html=True)

st.title("🎬 Myanmar Subtitle Generator & Translator")
st.write("Groq (Whisper) နှင့် Gemini AI သုံးပြီး Subtitle (.srt) ချက်ချင်းထုတ်ယူမည်")

# Timestamp ကို SRT format (00:00:00,000) သို့ ပြောင်းပေးသည့် Function
def format_timestamp(seconds):
    td = timedelta(seconds=seconds)
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    millisecs = int((td.total_seconds() - total_seconds) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"

# Verbose JSON မှ SRT စာသားပြောင်းပေးသည့် Function
def json_to_srt(segments):
    srt_output = ""
    for idx, segment in enumerate(segments, start=1):
        start_time = format_timestamp(segment.get('start', 0))
        end_time = format_timestamp(segment.get('end', 0))
        text = segment.get('text', '').strip()
        srt_output += f"{idx}\n{start_time} --> {end_time}\n{text}\n\n"
    return srt_output

# Sidebar - API Keys Setup
st.sidebar.header("🔑 API Keys")
groq_api_key = st.sidebar.text_input("Groq API Key", type="password")
gemini_api_key = st.sidebar.text_input("Gemini API Key", type="password")

uploaded_file = st.file_uploader("ဗီဒီယို သို့မဟုတ် အသံဖိုင် တင်ပါ (mp3, wav, mp4, m4a)", type=["mp3", "wav", "mp4", "m4a"])

if uploaded_file:
    if not groq_api_key or not gemini_api_key:
        st.warning("⚠️ ကျေးဇူးပြု၍ ဘယ်ဘက် Sidebar တွင် API Keys ဖြည့်သွင်းပါ။")
    else:
        if st.button("🚀 Subtitle ထုတ်ပြီး ဘာသာပြန်မည်"):
            with st.spinner("ဖိုင်ကို Processing လုပ်နေပါသည်။ ခေတ္တစောင့်ပါ..."):
                
                file_ext = os.path.splitext(uploaded_file.name)[1].lower()
                with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_file:
                    tmp_file.write(uploaded_file.read())
                    tmp_file_path = tmp_file.name

                audio_path = tmp_file_path
                compressed_audio_path = None

                try:
                    # ဖိုင်ဆိုဒ် 24MB ထက်ကြီးပါက ffmpeg ဖြင့် mp3 သို့ တိုက်ရိုက်ပြောင်းပြီး ချုံ့ခြင်း
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

                    # ၁။ Groq Whisper API ဖြင့် verbose_json တောင်းယူခြင်း
                    try:
                        groq_client = Groq(api_key=groq_api_key.strip())
                        with open(audio_path, "rb") as file:
                            transcription = groq_client.audio.transcriptions.create(
                                file=(audio_path, file.read()),
                                model="whisper-large-v3",
                                response_format="verbose_json"
                            )
                        
                        # JSON ကို SRT သို့ ပြောင်းခြင်း
                        segments = transcription.segments if hasattr(transcription, 'segments') else transcription.get('segments', [])
                        raw_srt = json_to_srt(segments)

                    except Exception as groq_err:
                        st.error(f"❌ Groq API Error: {str(groq_err)}")
                        st.stop()
                    
                    # ၂။ Gemini API ဖြင့် မြန်မာလို ဘာသာပြန်ခြင်း
                    try:
                        genai.configure(api_key=gemini_api_key.strip())
                        gemini_model = genai.GenerativeModel('gemini-1.5-flash')
                        
                        prompt = f"""
                        You are a professional subtitle translator. 
                        Translate the following SRT content into natural and fluent Burmese (Myanmar language).
                        
                        STRICT RULES:
                        1. Keep the SRT structure, sequence numbers, and timecodes EXACTLY the same.
                        2. Only translate the text lines, do not alter timestamps.
                        3. Use natural spoken Burmese suitable for movie subtitles.
                        
                        SRT Content:
                        {raw_srt}
                        """
                        
                        response = gemini_model.generate_content(prompt)
                        translated_srt = response.text
                    except Exception as gemini_err:
                        st.error(f"❌ Gemini API Error: {str(gemini_err)}")
                        st.stop()

                    # ရလဒ်ပြသခြင်း
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
