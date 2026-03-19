import streamlit as st
import google.genai as genai
from google.genai import types
import os
import time
import asyncio
import edge_tts

# --- SETUP MOVIEPY ---
try:
    from moviepy.video.io.VideoFileClip import VideoFileClip
    from moviepy.audio.io.AudioFileClip import AudioFileClip
    # Import vfx untuk versi 2.0
    import moviepy.video.fx as vfx
except ImportError:
    st.error("Gagal memuat MoviePy. Pastikan requirements.txt sudah benar.")
    st.stop()

st.set_page_config(page_title="AI Video Automator", layout="centered")

def init_gemini():
    try:
        return genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
    except:
        st.error("Gemini API Key belum diset di Secrets!")
        return None

async def generate_voice(text, output_path, voice_name):
    communicate = edge_tts.Communicate(text, voice_name)
    await communicate.save(output_path)

# --- UI ---
with st.sidebar:
    st.header("⚙️ Pengaturan")
    lang = st.selectbox("Bahasa", ["Indonesia", "Inggris"])
    if lang == "Indonesia":
        voice_option = st.radio("Pilih Suara", ["Pria (Ardi)", "Wanita (Gadis)"])
        v_name = "id-ID-ArdiNeural" if "Pria" in voice_option else "id-ID-GadisNeural"
    else:
        voice_option = st.radio("Pilih Suara", ["Pria (Guy)", "Wanita (Ava)"])
        v_name = "en-US-GuyNeural" if "Pria" in voice_option else "en-US-AvaNeural"
    style = st.text_input("Gaya Bahasa", "Energik & Persuasif")
    goal = st.text_input("Tujuan Video", "Review Produk")
    extra_cmd = st.text_area("Instruksi Tambahan (CTA)", "")

st.title("🎬 AI Video Automation")
uploaded_file = st.file_uploader("Upload Video", type=["mp4", "mov", "mpeg4"])

if uploaded_file and st.button("🚀 Mulai Proses"):
    g_client = init_gemini()
    if g_client:
        res_p, aud_p, out_p = "res.mp4", "vo.mp3", "final.mp4"

        with st.status("Memproses...", expanded=True) as status:
            # 1. RESIZING (FIXED FOR V2.0)
            st.write("🔧 Resizing Video...")
            with open("temp.mp4", "wb") as f:
                f.write(uploaded_file.read())
            
            clip = VideoFileClip("temp.mp4")
            
            # Mendapatkan durasi dengan aman
            try:
                dur = clip.duration() if callable(clip.duration) else clip.duration
            except:
                dur = clip.end - clip.start
            
            # Resizing yang kompatibel dengan semua versi MoviePy
            try:
                # Cara MoviePy v2.0
                clip = clip.with_effects([vfx.Resize(height=720)])
            except:
                try:
                    # Cara MoviePy v1.0
                    clip = clip.resize(height=720)
                except:
                    # Jika gagal semua, gunakan ukuran asli agar tidak error
                    st.warning("Gagal resize, menggunakan resolusi asli.")
                    pass
            
            clip.write_videofile(res_p, codec="libx264", audio=False)

            # 2. GEMINI ANALYSIS
            st.write("🧠 Gemini Analysis...")
            v_upload = g_client.files.upload(file=res_p)
            while v_upload.state.name == "PROCESSING":
                time.sleep(2)
                v_upload = g_client.files.get(name=v_upload.name)
            
            prompt_text = f"Buat narasi {goal} bahasa {lang}, gaya {style}. Durasi {dur:.1f} detik. Berikan naskah saja."
            response = g_client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=[types.Content(role="user", parts=[
                    types.Part.from_uri(file_uri=v_upload.uri, mime_type=v_upload.mime_type),
                    types.Part.from_text(text=prompt_text)
                ])]
            )
            narasi = response.text
            st.info(f"Narasi: {narasi}")

            # 3. EDGE-TTS
            st.write("🎙️ Membuat Voiceover (Edge-TTS)...")
            asyncio.run(generate_voice(narasi, aud_p, v_name))

            # 4. MERGING (FIXED FOR V2.0)
            if os.path.exists(aud_p):
                st.write("🎬 Menggabungkan Video & Audio...")
                a_clip = AudioFileClip(aud_p)
                
                try:
                    # Gabungkan audio dan video dengan cara paling aman
                    if hasattr(clip, 'with_audio'):
                        final = clip.with_audio(a_clip)
                    else:
                        final = clip.set_audio(a_clip)
                    
                    # Pastikan durasi audio tidak melebihi video
                    final = final.with_duration(dur) if hasattr(final, 'with_duration') else final.set_duration(dur)
                    
                    final.write_videofile(out_p, codec="libx264", audio_codec="aac")
                    status.update(label="✅ Selesai!", state="complete")
                except Exception as e:
                    st.error(f"Gagal saat penggabungan: {e}")
                    st.stop()

        # --- HASIL ---
        st.divider()
        if os.path.exists(out_p):
            st.video(out_p)
            with open(out_p, "rb") as f:
                st.download_button("💾 Download Video", f, "hasil_ai.mp4", "video/mp4")
