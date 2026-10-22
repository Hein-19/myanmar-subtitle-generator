import time
import requests
import streamlit as st


def translate_srt_with_openrouter(
    api_key, raw_srt, model_name="minimax/minimax-m3.1-flash:free", chunk_size=25
):
  blocks = [b.strip() for b in raw_srt.strip().split("\n\n") if b.strip()]
  translated_blocks = []
  total_blocks = len(blocks)

  progress_bar = st.progress(0)
  status_placeholder = st.empty()

  # OpenRouter API Endpoint
  url = "https://openrouter.ai/api/v1/chat/completions"
  headers = {
      "Authorization": f"Bearer {api_key.strip()}",
      "Content-Type": "application/json",
      "HTTP-Referer": "https://streamlit.io",  # Optional: for app ranking on openrouter
      "X-Title": "Myanmar Subtitle Studio",  # Optional
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
        f"🇲🇲 OpenRouter ({model_name}) ဖြင့် ဘာသာပြန်နေစဉ်... ({start_block} မှ"
        f" {end_block} / {total_blocks} စာကြောင်းများ)"
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
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        res_json = response.json()

        if response.status_code == 200:
          translated_chunk = (
              res_json["choices"][0]["message"]["content"].strip()
          )
          if translated_chunk.startswith("```"):
            lines = translated_chunk.split("\n")
            translated_chunk = "\n".join(
                [line for line in lines if not line.strip().startswith("```")]
            ).strip()

          translated_blocks.append(translated_chunk)
          chunk_success = True
          time.sleep(2)  # Free tier အတွက် ခေတ္တ အနားပေးခြင်း
          break
        else:
          err_msg = res_json.get("error", {}).get("message", str(res_json))
          time.sleep(3)
      except Exception as e:
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
