import streamlit as st
import pysrt
import requests
import tempfile
import os

# Streamlit UI မျက်နှာပြင် ပြင်ဆင်ခြင်း
st.set_page_config(page_title="SRT Translator (DeepSeek)", page_icon="📝")
st.title("📝 AI Subtitle Translator")
st.markdown("SRT စာတန်းထိုးဖိုင်များကို Timestamp မပျက်စီးစေဘဲ **DeepSeek (OpenRouter)** ဖြင့် ဘာသာပြန်ပေးမည့် Web App ဖြစ်ပါသည်။")

# ဘေးဘက် (Sidebar) တွင် API Key နှင့် Settings များတောင်းခံခြင်း
with st.sidebar:
    st.header("⚙️ Settings")
    api_key = st.text_input("OpenRouter API Key", type="password", placeholder="sk-or-v1-...")
    target_lang = st.text_input("Target Language", value="Myanmar (Burmese)")
    chunk_size = st.number_input("Lines per request (Chunk Size)", min_value=10, max_value=100, value=40, help="Token သက်သာစေရန်နှင့် Context မိစေရန် စာကြောင်းမည်မျှစု၍ ပို့မည်ကို သတ်မှတ်ပါ။")

# ပင်မစာမျက်နှာ ဖိုင် Upload လုပ်ရန်
uploaded_file = st.file_uploader("Upload your .srt file", type=["srt"])

def translate_srt(srt_text, target_language, api_key, chunk_size):
    # ၁။ စာသားကို pysrt ဖြင့် ဖတ်ရန်
    subs = pysrt.from_string(srt_text)
    
    # ၂။ Timestamp ဖယ်ပြီး စာသားရှေ့တွင် နံပါတ်ကပ်ခြင်း (Index Tagging)
    indexed_lines = []
    for i, sub in enumerate(subs):
        clean_text = sub.text.replace('\n', ' ')
        indexed_lines.append(f"{i}|{clean_text}")
    
    # ၃။ စာကြောင်းများကို အုပ်စု (Chunk) ခွဲခြင်း
    chunks = [indexed_lines[i:i + chunk_size] for i in range(0, len(indexed_lines), chunk_size)]
    
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    system_prompt = f"""You are a professional subtitle translator. Translate the text naturally into {target_language}.
CRITICAL RULES:
1. Keep the exact index number and the pipe symbol '|' at the beginning of each line.
2. DO NOT merge or split lines.
3. Return ONLY the translated lines. Do not add any extra explanations or quotes."""

    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total_chunks = len(chunks)
    
    # ၄။ Chunk တစ်ခုချင်းစီကို API သို့ ပို့ခြင်း
    for idx, chunk in enumerate(chunks):
        status_text.text(f"Translating part {idx + 1} of {total_chunks}...")
        
        user_prompt = "\n".join(chunk)
        payload = {
            "model": "deepseek/deepseek-chat", # OpenRouter ပေါ်ရှိ DeepSeek မော်ဒယ်
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.0 # တိကျစေရန်
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload)
            if response.status_code == 200:
                result_text = response.json()['choices'][0]['message']['content'].strip()
                
                # ၅။ ရလာသောစာသားများကို မူရင်း Timestamp ထဲ ပြန်ထည့်ခြင်း
                for line in result_text.split('\n'):
                    if '|' in line:
                        parts = line.split('|', 1)
                        if len(parts) == 2:
                            idx_str, translated_text = parts
                            try:
                                sub_idx = int(idx_str.strip())
                                subs[sub_idx].text = translated_text.strip()
                            except ValueError:
                                pass
            else:
                st.error(f"API Error at part {idx + 1}: {response.text}")
                return None
        except Exception as e:
            st.error(f"Connection Error: {e}")
            return None
            
        progress_bar.progress((idx + 1) / total_chunks)
        
    status_text.success("🎉 Translation Complete!")
    
    # ၆။ ဘာသာပြန်ပြီးသား SRT ကို string အဖြစ် ပြန်ထုတ်ပေးခြင်း
    # pysrt မှ တိုက်ရိုက် string ပြန်ထုတ်ရန် temp file ကို အသုံးပြုပါမည်
    with tempfile.NamedTemporaryFile(delete=False, suffix=".srt", mode="w", encoding="utf-8") as tmp:
        subs.save(tmp.name, encoding="utf-8")
        tmp.seek(0)
        translated_srt_data = open(tmp.name, "r", encoding="utf-8").read()
    
    # ယာယီဖိုင်ကို ပြန်ဖျက်ခြင်း
    os.remove(tmp.name)
    
    return translated_srt_data

# Translate ခလုတ်နှိပ်သောအခါ အလုပ်လုပ်မည့်အပိုင်း
if st.button("🚀 Start Translation"):
    if not api_key:
        st.warning("⚠️ ကျေးဇူးပြု၍ ဘေးဘက် (Sidebar) တွင် OpenRouter API Key ထည့်ပါ။")
    elif not uploaded_file:
        st.warning("⚠️ ကျေးဇူးပြု၍ .srt ဖိုင်တစ်ခုကို Upload လုပ်ပါ။")
    else:
        # Upload လုပ်ထားသော ဖိုင်ကို ဖတ်ခြင်း
        original_srt_text = uploaded_file.read().decode("utf-8")
        
        with st.spinner("Processing..."):
            translated_srt = translate_srt(original_srt_text, target_lang, api_key, int(chunk_size))
            
            if translated_srt:
                # မူရင်းဖိုင်နာမည်ကို ယူ၍ _translated_my.srt ဟု ပြောင်းခြင်း
                old_filename = uploaded_file.name
                new_filename = old_filename.replace(".srt", "_translated.srt")
                
                st.markdown("### 📥 Download Ready!")
                st.download_button(
                    label="Download Translated SRT File",
                    data=translated_srt,
                    file_name=new_filename,
                    mime="text/plain"
                )
