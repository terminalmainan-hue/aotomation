import streamlit as st
import google.genai as genai
from google.genai import types
import os, time, asyncio, edge_tts, re

# --- 1. CLEANING SESSION (Mencegah OSError) ---
for f in ["temp.mp4", "res.mp4", "vo.mp3", "final.mp4"]:
    if os.path.exists(f):
        try: os.remove(f)
        except: pass

try:
    from moviepy.video.io.VideoFileClip import VideoFileClip
    from moviepy.audio.io.AudioFileClip import AudioFileClip
    import moviepy.video.fx as vfx
except ImportError:
    st.error("Library MoviePy v2.0+ diperlukan.")
    st.stop()

st.set_page_config(page_title="AI Video Automator", layout="centered")

def init_gemini():
    try: return genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
    except: return None

async def generate_voice(text, output_path, voice_name):
    communicate = edge_tts.Communicate(text, voice_name)
    await communicate.save(output_path)

# --- UI SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Pengaturan")
    lang = st.selectbox("Bahasa", ["Indonesia", "Inggris"])
    v_name = "id-ID-ArdiNeural" if lang == "Indonesia" else "en-US-GuyNeural"
    style = st.text_input("Gaya Bahasa", "Energik & Persuasif")
    goal = st.text_input("Tujuan Video", "Review Hot Wheels")
    extra_cmd = st.text_area("Instruksi Tambahan / CTA", "Jangan lupa subscribe!")

st.title("🎬 AI Video Automation")
uploaded_file = st.file_uploader("Upload Video", type=["mp4", "mov"])

if uploaded_file and st.button("🚀 Mulai Proses"):
    g_client = init_gemini()
    if g_client:
        res_p, aud_p, out_p = "res.mp4", "vo.mp3", "final.mp4"

        with st.status("Sedang diproses...", expanded=True) as status:
            # A. PREPARING VIDEO
            with open("temp.mp4", "wb") as f:
                f.write(uploaded_file.read())
            
            clip = VideoFileClip("temp.mp4")
            dur = clip.duration # Contoh: 30 detik
            
            # Resize ke 720p (Standar MoviePy 2.0)
            clip_res = clip.with_effects([vfx.Resize(height=720)])
            clip_res.write_videofile(res_p, codec="libx264", audio=False)

            # B. GEMINI ANALYSIS (LOGIKA 30 DETIK)
            # Kita ingin: 3 detik awal diam + 22 detik bicara + 5 detik akhir diam
            # Total bicara = 25 detik (untuk video 30 detik)
            start_silence = 3.0
            end_silence = 5.0
            target_dur = max(dur - (start_silence + end_silence), 5.0)
            
            # Hitung batas kata (1.8 kata per detik agar santai/tidak balapan)
            word_limit = int(target_dur * 1.8)

            prompt = f"""
            Buat naskah {goal} {lang} gaya {style}.
            DURASI BICARA: Harus selesai dalam {target_dur} detik.
            BATAS KATA: Maksimal {word_limit} kata saja.
            PENTING: Berikan teks saja. Jangan tulis 'Narasi' atau kode waktu.
            CTA: {extra_cmd}
            """
            
            v_upload = g_client.files.upload(file=res_p)
            while v_upload.state.name == "PROCESSING":
                time.sleep(2)
                v_upload = g_client.files.get(name=v_upload.name)

            response = g_client.models.generate_content(
                model="gemini-3-flash-preview", # Gunakan flash untuk kecepatan
                contents=[types.Content(role="user", parts=[
                    types.Part.from_uri(file_uri=v_upload.uri, mime_type=v_upload.mime_type),
                    types.Part.from_text(text=prompt)
                ])]
            )
            
            narasi = re.sub(r'Narasi:|Naskah:|\d{2}:\d{2}', '', response.text).strip()
            st.info(f"Naskah ({len(narasi.split())} kata): {narasi}")

            # C. VOICE GENERATION
            asyncio.run(generate_voice(narasi, aud_p, v_name))

            # D. MERGING (ANTI ACCESSING TIME ERROR)
            if os.path.exists(aud_p):
                a_clip = AudioFileClip(aud_p).with_start(start_silence)
                
                try:
                    # Gabungkan audio
                    final = clip_res.with_audio(a_clip)
                    
                    # POTONG PAKSA di detik ke-30 (dur)
                    # Ini menghilangkan error t=30.01-30.05
                    final = final.subclipped(0, dur)
                    
                    final.write_videofile(out_p, codec="libx264", audio_codec="aac", fps=24)
                    status.update(label="✅ Selesai!", state="complete")
                except Exception as e:
                    st.error(f"Gagal Merging: {e}")
                    st.stop()

        # E. HASIL & DOWNLOAD
        st.divider()
        if os.path.exists(out_p):
            st.video(out_p)
            with open(out_p, "rb") as f:
                st.download_button("💾 Download Video", f, "hasil_30detik.mp4")
