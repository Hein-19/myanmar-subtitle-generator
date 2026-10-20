# Groq ဖြင့် အမှားအယွင်းမရှိ အမြန်ဘာသာပြန်မည့် Function (Model Fallback ပါဝင်သည်)
def translate_srt_with_groq_llama(groq_client, raw_srt, chunk_size=20):
  blocks = [b.strip() for b in raw_srt.strip().split("\n\n") if b.strip()]
  translated_blocks = []

  total_blocks = len(blocks)
  progress_bar = st.progress(0)
  status_placeholder = st.empty()

  # စမ်းသပ်အသုံးပြုမည့် Groq Models များ (တစ်ခု 404 ဖြစ်ပါက နောက်တစ်ခုသို့ အလိုအလျောက် ကူးမည်)
  candidate_models = [
      "llama-3.1-8b-instant",  # အမြဲတမ်း ရရှိနိုင်ပြီး အလွန်မြန်သော မော်ဒယ်
      "llama-3.3-70b-versatile",
      "llama-3.1-70b-versatile",
      "mixtral-8x7b-32768",
  ]

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

    system_prompt = """You are a professional Burmese subtitle translator.
Translate the following SRT subtitles into natural, conversational Burmese (Myanmar language).

STRICT RULES:
1. Maintain the exact same SRT sequence numbers and timestamps.
2. Only translate the subtitle text lines.
3. If a sentence is long, wrap it into two lines using a newline (\\n).
4. Do not output any explanation, markdown notes, or introductory words. Return pure SRT only."""

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
        time.sleep(0.5)
        break  # အောင်မြင်ပါက နောက် candidate model များကို မစမ်းတော့ဘဲ ထွက်မည်

      except Exception as e:
        err_msg = str(e).lower()
        # အကယ်၍ 404 (Model not found) ဖြစ်ပါက နောက် model တစ်ခုဖြင့် ချက်ချင်း ပြောင်းစမ်းမည်
        if "404" in err_msg or "not found" in err_msg:
          continue
        else:
          time.sleep(2)

    # မော်ဒယ်အားလုံး မရပါကသာ မူရင်းအတိုင်း ထည့်မည်
    if not chunk_success:
      translated_blocks.append(chunk_text)

  progress_bar.empty()
  status_placeholder.empty()
  return "\n\n".join(translated_blocks) + "\n\n"
