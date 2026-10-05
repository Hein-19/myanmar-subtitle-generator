import streamlit as st
from groq import Groq
import google.generativeai as genai
import tempfile
import os
from pydub import AudioSegment

st.set_page_config(page_title="Myanmar Subtitle AI", page_icon="🎬", layout="centered")

st.markdown("""
    
""", unsafe_allow_html=True)

st.title("🎬 Myanmar Subtitle Generator & Translator")
st.write("Groq (Whisper) နှင့် Gemini AI သုံးပြီး Subtitle (.srt) ချက်ချင်းထုတ်ယူမည်")

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
                
                # ယာယီ ဖိုင်သိမ်းခြင်း
                file_ext = os.path.splitext(uploaded_file.name)[1].lower()
                with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_file:
                    tmp_file.write(uploaded_file.read())
                    tmp_file_path = tmp_file.name

                audio_path = tmp_file_path

                try:
                    # ဖိုင်ဆိုဒ် 24MB ထက်ကြီးပါက အသံဖိုင်အဖြစ် သီးသန့်ပြောင်းပြီး ဖိုင်ဆိုဒ်ချုံ့ခြင်း
                    if os.path.getsize(tmp_file_path) > 24 * 1024 * 1024:
                        st.info("ဖိုင်ဆိုဒ်ကြီးသောကြောင့် အသံဖိုင်အဖြစ် ပြောင်းလဲချုံ့နေပါသည်...")
                        audio = AudioSegment.from_file(tmp_file_path)
                        compressed_audio_path = tmp_file_path + "_compressed.mp3"
                        audio.export(compressed_audio_path, format="mp3", bitrate="64k")
                        audio_path = compressed_audio_path

                    # ၁။ Groq Whisper API ဖြင့် Subtitle (SRT) ထုတ်ယူခြင်း
                    groq_client = Groq(api_key=groq_api_key)
                    with open(audio_path, "rb") as file:
                        transcription = groq_client.audio.transcriptions.create(
                            file=(audio_path, file.read()),
                            model="whisper-large-v3",
                            response_format="srt"
                        )
                    
                    raw_srt = transcription
                    
                    # ၂။ Gemini API ဖြင့် မြန်မာလို ဘာသာပြန်ခြင်း
                    genai.configure(api_key=gemini_api_key)
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
                    # ယာယီဖိုင်များ ပြန်ဖျက်ခြင်း
                    if os.path.exists(tmp_file_path):
                        os.remove(tmp_file_path)
                    if 'compressed_audio_path' in locals() and os.path.exists(compressed_audio_path):
                        os.remove(compressed_audio_path)
