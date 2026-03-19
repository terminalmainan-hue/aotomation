import streamlit as st
import google.genai as genai
from google.genai import types
import os, time, asyncio, edge_tts, re

# --- 1. CLEANING SESSION ---
# Hapus file lama agar tidak OSError, tapi pastikan variabel path tetap ada
files_to_clean = ["temp.mp4", "res.mp4", "vo.mp3", "final.mp4"]
for f in files_to_clean:
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
    style = st.text_input("Gaya Bahasa", "Energik")
    goal = st.text_input("Tujuan Video", "Review Hot Wheels")
    extra_cmd = st.text_area("Instruksi CTA", "Klik link di bio!")

st.title("🎬 AI Video Automation")
uploaded_file = st.file_uploader("Upload Video", type=["mp4", "mov"])

if uploaded_file and st.button("🚀 Mulai Proses"):
    g_client = init_gemini()
    if g_client:
        res_p, aud_p, out_p = "res.mp4", "vo.mp3", "final.mp4"

        with st.status("Memproses...", expanded=True) as status:
            # A. VIDEO PREP
            with open("temp.mp4", "wb") as f:
                f.write(uploaded_file.read())
            
            clip = VideoFileClip("temp.mp4")
            dur = clip.duration 
            
            # Resizing dengan MoviePy v2.0
            clip_res = clip.with_effects([vfx.Resize(height=720)])
            clip_res.write_videofile(res_p, codec="libx264", audio=False)
            
            # Beri jeda 1 detik agar sistem file mencatat res.mp4
            time.sleep(1)

            # B. GEMINI (Logika 30 Detik)
            # Jeda 3s awal + 5s akhir = 8s diam. Sisa bicara = dur - 8.
            target_dur = max(dur - 8.0, 5.0)
            word_limit = int(target_dur * 1.7) # Lebih santai agar tidak tabrakan

            prompt = f"Buat naskah {goal} {lang} gaya {style}. Maksimal {word_limit} kata. Berikan teks saja. Selesai bicara dalam {target_dur} detik. CTA: {extra_cmd}"
            
            # FIX: Gunakan file= (bukan path=)
            v_upload = g_client.files.upload(file=res_p)
            while v_upload.state.name == "PROCESSING":
                time.sleep(2)
                v_upload = g_client.files.get(name=v_upload.name)

            response = g_client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=[types.Content(role="user", parts=[
                    types.Part.from_uri(file_uri=v_upload.uri, mime_type=v_upload.mime_type),
                    types.Part.from_text(text=prompt)
                ])]
            )
            
            narasi = re.sub(r'Narasi:|Naskah:|\d{2}:\d{2}', '', response.text).strip()
            st.info(f"Naskah: {narasi}")

            # C. VOICE
            asyncio.run(generate_voice(narasi, aud_p, v_name))

            # D. MERGING (Solusi Milidetik)
            if os.path.exists(aud_p):
                a_clip = AudioFileClip(aud_p).with_start(3.0)
                try:
                    # Kunci durasi total dan subclip untuk cegah error t=30.01
                    final = clip_res.with_audio(a_clip).with_duration(dur).subclipped(0, dur)
                    final.write_videofile(
    out_p, 
    codec="libx264", 
    audio_codec="aac", 
    fps=24, 
    temp_audiofile='temp-audio.m4a', # Menentukan nama file audio sementara
    remove_temp=True # Otomatis hapus setelah selesai
)
                    status.update(label="✅ Berhasil!", state="complete")
                except Exception as e:
                    st.error(f"Gagal Merging: {e}")
                    st.stop()

        # E. DOWNLOAD
        st.divider()
        if os.path.exists(out_p):
            st.video(out_p)
            with open(out_p, "rb") as f:
                st.download_button("💾 Download Video", f, "hasil_ai.mp4")
