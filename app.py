import streamlit as st
import google.generativeai as genai
import time
import asyncio
import edge_tts
import os
from moviepy.editor import VideoFileClip, AudioFileClip, CompositeAudioClip

# --- 1. KEAMANAN API KEY (STREAMLIT SECRETS) ---
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
else:
    st.error("❌ API Key tidak ditemukan! Masukkan GEMINI_API_KEY di menu Settings > Secrets pada Streamlit Cloud.")
    st.stop()

async def generate_voice(text, voice_name, output_path):
    communicate = edge_tts.Communicate(text, voice_name, rate="+0%")
    await communicate.save(output_path)

st.set_page_config(page_title="AI Video Automator", layout="wide")
st.title("🎬 Zar's Video Automator Pro")

# --- BAGIAN 1: INPUT VIDEO ---
st.subheader("1. Input Video")
uploaded_file = st.file_uploader("Pilih file video", type=['mp4', 'mov', 'avi'])
video_path = "temp_video.mp4"

if uploaded_file:
    with open(video_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

def process_video(uploaded_file, lang, voice_type, style, goal, extra_cmd):
    # Simpan file sementara
    with open("input_raw.mp4", "wb") as f:
        f.write(uploaded_file.read())
    
    with st.status("Sedang bekerja...", expanded=True) as status:
        # Save temp file
        with open("input.mp4", "wb") as f:
            f.write(uploaded_file.read())
            
        # 1. Resize (MoviePy v2 style)
        st.write("🔧 Resizing...")
        clip = VideoFileClip("input.mp4")
        # Jika versi 2.x gunakan ini:
        try:
            clip = clip.with_effects([vfx.Resize(height=720)])
        except:
            # Fallback jika ternyata yang terinstal v1.x
            clip = clip.resize(height=720)
            
        duration = clip.duration
        clip.write_videofile("resized.mp4", codec="libx264", audio=False

# --- BAGIAN 2: PENGATURAN KONTEN ---
st.subheader("2. Menu Pengaturan Konten")
col1, col2, col3 = st.columns(3)

with col1:
    voice_opt = st.selectbox("Pilih Karakter Suara:", ["Pria (Ardi)", "Wanita (Gadis)"])
    voice_map = {"Pria (Ardi)": "id-ID-ArdiNeural", "Wanita (Gadis)": "id-ID-GadisNeural"}
    gaya = st.selectbox("Gaya Bicara:", ["Energetik/Semangat", "Ceria/Friendly", "Dramatis", "Deep/Filosofis", "Formal/Profesional", "Santai/Conversational", "Otoriter/Tegas", "Persuasif (Sales)", "Misterius/Suspense", "Sarkas/Lucu"])

with col2:
    bahasa = st.selectbox("Pilih Bahasa:", ["Bahasa Indonesia", "Bahasa Sunda", "Bahasa Jawa", "Bahasa Inggris"])
    kategori = st.selectbox("Tujuan Video:", ["Review Produk (Detail)", "Fakta Unik", "Soft Sell (Showcase)", "Hard Sell (Persuasif)", "Cinematic Showcase", "Storytelling/Bercerita", "Stand Up Comedy/Parodi", "Motivasi & Inspirasi", "Menjawab Pertanyaan (Q&A)", "Opini atau Reaksi (Reaction)", "Klarifikasi", "Ucapan Terima Kasih (Appreciation)", "Hunting/Daily Vlog"])

with col3:
    st.write(" ")
    st.write(" ")
    create_btn = st.button("🚀 GENERATE FINAL VIDEO", use_container_width=True)

instruksi_user = st.text_area("✍️ Instruksi Tambahan (Opsional):", placeholder="Contoh: Sebutkan 'Gaskeun', mention channel 'Zar Diecast'...")

# --- BAGIAN 3: PROSES AI & RENDERING ---
if create_btn and uploaded_file:
    # Load Video dengan orientasi yang benar
    video_clip = VideoFileClip(video_path)

    durasi_video = video_clip.duration

    with st.status("🤖 AI sedang memproses...", expanded=True) as status:
        # 1. Analisis Gemini
        video_ai = genai.upload_file(path=video_path)
        while video_ai.state.name == "PROCESSING":
            time.sleep(2)
            video_ai = genai.get_file(video_ai.name)

        model = genai.GenerativeModel(model_name="gemini-3-flash-preview")
        prompt = f"Buat narasi {kategori} dalam {bahasa} gaya {gaya}. Durasi {durasi_video:.1f} detik. Instruksi: {instruksi_user}. HANYA output teks narasi."
        
        response = model.generate_content([video_ai, prompt])
        naskah_clean = response.text.replace('"', '').strip()

        st.write(f"📝 **Naskah AI:** {naskah_clean}")

        # 2. Voice Over
        st.write("🔊 Menghasilkan suara...")
        asyncio.run(generate_voice(naskah_clean, voice_map[voice_opt], "vo.mp3"))

        # 3. Audio Mixing & Lock Duration
        st.write("🎬 Merender video (Menjaga Resolusi)...")
        audio_clip = AudioFileClip("vo.mp3")
        audio_final = CompositeAudioClip([audio_clip.set_start(0)]).set_duration(durasi_video)

        # 4. Final Render (Mengunci FPS dan Ukuran Asli)
        final_video = video_clip.set_audio(audio_final)
        output_name = "final_output.mp4"
        
        final_video.write_videofile(
            output_name, 
            codec="libx264", 
            audio_codec="aac", 
            fps=video_clip.fps, 
            preset="ultrafast",
            threads=4
        )
        
        status.update(label="✅ Selesai!", state="complete")

    st.success("Berhasil! Silakan cek hasil di bawah:")
    st.video(output_name)

    with open(output_name, "rb") as file:
        st.download_button(label="📥 Download Video", data=file, file_name=f"ZarAI_{int(time.time())}.mp4")
# --- FITUR AUTO-CLEANUP (Ramah Server) ---
    # Beri jeda sebentar agar browser sempat memulai proses download
    time.sleep(2) 
    
    # Kumpulkan daftar file yang harus dihapus
    files_to_clean = [video_path, "vo.mp3", output_name]
    
    for file in files_to_clean:
        if os.path.exists(file):
            try:
                os.remove(file)
            except Exception as e:
                # Gagal hapus biasanya karena file masih dikunci sistem
                pass

    # Bersihkan Cache Streamlit untuk membebaskan RAM server
    st.cache_data.clear()
    st.cache_resource.clear()
    # Tutup klip agar memori tidak penuh
    video_clip.close()
