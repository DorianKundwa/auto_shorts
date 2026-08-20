import React, { useState, useCallback, useEffect } from 'react';
import { useDropzone } from 'react-dropzone';
import { motion, AnimatePresence } from 'framer-motion';
import { UploadCloud, Scissors, RefreshCw, Download, CheckCircle, Video, Type, Share2, Sparkles, Layers } from 'lucide-react';
import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';
const BACKEND_URL = API_URL.replace(/\/api$/, '');

const AVAILABLE_FONTS = [
  { id: 'Montserrat-Black.ttf', name: 'Montserrat Black' },
  { id: 'Roboto-Black.ttf', name: 'Roboto Black' },
  { id: 'Super Bouncer.ttf', name: 'Super Bouncer' },
  { id: 'Helvetica Punk.ttf', name: 'Helvetica Punk' }
];

const DESTINATIONS = [
  { id: 'TikTok', name: 'TikTok', ratio: '9:16' },
  { id: 'Instagram', name: 'Instagram', ratio: '1:1' },
  { id: 'YouTube', name: 'YouTube', ratio: '16:9' }
];

function App() {
  const [file, setFile] = useState(null);
  const [jobId, setJobId] = useState(null);
  const [jobStatus, setJobStatus] = useState(null);
  const [error, setError] = useState('');
  
  // Transcript Upload State
  const [transcriptFile, setTranscriptFile] = useState(null);
  
  // New Form State
  const [selectedFont, setSelectedFont] = useState(AVAILABLE_FONTS[0].id);
  const [selectedDestinations, setSelectedDestinations] = useState(['TikTok']);

  const toggleDestination = (destId) => {
    setSelectedDestinations(prev => 
      prev.includes(destId) 
        ? prev.filter(d => d !== destId)
        : [...prev, destId]
    );
  };

  const onDrop = useCallback(acceptedFiles => {
    if (acceptedFiles.length > 0) {
      setFile(acceptedFiles[0]);
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'video/*': ['.mp4', '.mov', '.mkv'] },
    maxFiles: 1
  });

  const handleUpload = async () => {
    if (!file) return;
    if (selectedDestinations.length === 0) {
      setError("Please select at least one destination platform.");
      return;
    }
    
    const formData = new FormData();
    formData.append('file', file);
    if (transcriptFile) {
      formData.append('transcript', transcriptFile);
    }
    formData.append('font', selectedFont);
    formData.append('destinations', selectedDestinations.join(','));
    
    try {
      setError('');
      const res = await axios.post(`${API_URL}/upload`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      setJobId(res.data.job_id);
    } catch (err) {
      setError('Upload failed. Is the backend running?');
    }
  };

  useEffect(() => {
    let interval;
    if (jobId && jobStatus?.status !== 'completed' && jobStatus?.status !== 'failed') {
      interval = setInterval(async () => {
        try {
          const res = await axios.get(`${API_URL}/status/${jobId}`);
          setJobStatus(res.data);
        } catch (e) {
          console.error(e);
        }
      }, 2000);
    }
    return () => clearInterval(interval);
  }, [jobId, jobStatus]);

  return (
    <div className="min-h-screen bg-slate-950 text-white font-sans selection:bg-purple-500/30">
      {/* Dynamic Background Glows */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none z-0">
        <div className="absolute top-[-20%] left-[-10%] w-[50%] h-[50%] rounded-full bg-purple-600/20 blur-[120px]" />
        <div className="absolute bottom-[-20%] right-[-10%] w-[60%] h-[60%] rounded-full bg-blue-600/10 blur-[150px]" />
      </div>

      <div className="container mx-auto px-6 py-16 max-w-6xl relative z-10">
        <header className="text-center mb-16">
          <motion.div
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ duration: 0.5 }}
            className="inline-flex items-center gap-3 px-4 py-2 rounded-full bg-slate-800/50 border border-slate-700/50 backdrop-blur-md mb-6"
          >
            <Sparkles className="w-5 h-5 text-purple-400" />
            <span className="text-sm font-medium tracking-wide text-slate-300">AI Video Generation Engine V2</span>
          </motion.div>
          <h1 className="text-6xl font-black mb-6 tracking-tight leading-tight">
            Auto <span className="bg-clip-text text-transparent bg-gradient-to-r from-blue-400 via-indigo-500 to-purple-500">Shorts</span>
          </h1>
          <p className="text-slate-400 text-xl max-w-2xl mx-auto leading-relaxed">
            Upload your long-form video and instantly generate 3 viral hooks perfectly formatted for any social platform.
          </p>
        </header>

        <main className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          
          {/* Left Column: Form & Upload */}
          <div className="lg:col-span-5 space-y-6">
            {!jobId && (
              <motion.div 
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                className="bg-slate-900/60 backdrop-blur-xl border border-slate-800 rounded-3xl p-8 shadow-2xl"
              >
                
                {/* Font Selection */}
                <div className="mb-8">
                  <h3 className="text-lg font-semibold mb-4 flex items-center gap-2 text-slate-200">
                    <Type className="w-5 h-5 text-indigo-400" /> Caption Font
                  </h3>
                  <div className="grid grid-cols-2 gap-3">
                    {AVAILABLE_FONTS.map(font => (
                      <button
                        key={font.id}
                        onClick={() => setSelectedFont(font.id)}
                        className={`px-4 py-3 rounded-xl border text-sm font-medium transition-all duration-300 ${
                          selectedFont === font.id 
                            ? 'bg-indigo-500/20 border-indigo-500 text-indigo-300 shadow-[0_0_15px_rgba(99,102,241,0.2)]' 
                            : 'bg-slate-800/50 border-slate-700 text-slate-400 hover:bg-slate-800 hover:border-slate-600'
                        }`}
                      >
                        {font.name}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Destination Selection */}
                <div className="mb-8">
                  <h3 className="text-lg font-semibold mb-4 flex items-center gap-2 text-slate-200">
                    <Share2 className="w-5 h-5 text-pink-400" /> Platforms
                  </h3>
                  <div className="flex flex-col gap-3">
                    {DESTINATIONS.map(dest => (
                      <button
                        key={dest.id}
                        onClick={() => toggleDestination(dest.id)}
                        className={`flex items-center justify-between px-5 py-4 rounded-xl border transition-all duration-300 ${
                          selectedDestinations.includes(dest.id)
                            ? 'bg-pink-500/10 border-pink-500 shadow-[0_0_15px_rgba(236,72,153,0.15)]'
                            : 'bg-slate-800/50 border-slate-700 hover:bg-slate-800 hover:border-slate-600'
                        }`}
                      >
                        <div className="flex items-center gap-3">
                          <div className={`w-5 h-5 rounded flex items-center justify-center border ${
                            selectedDestinations.includes(dest.id) ? 'bg-pink-500 border-pink-500' : 'border-slate-500 bg-slate-900'
                          }`}>
                            {selectedDestinations.includes(dest.id) && <CheckCircle className="w-3 h-3 text-white" />}
                          </div>
                          <span className={selectedDestinations.includes(dest.id) ? 'text-white font-medium' : 'text-slate-400'}>
                            {dest.name}
                          </span>
                        </div>
                        <span className="text-xs font-mono text-slate-500 bg-slate-900 px-2 py-1 rounded">{dest.ratio}</span>
                      </button>
                    ))}
                  </div>
                </div>

                {/* File Upload */}
                <div className="mb-8">
                  <h3 className="text-lg font-semibold mb-4 flex items-center gap-2 text-slate-200">
                    <Video className="w-5 h-5 text-blue-400" /> Source Video
                  </h3>
                  <div 
                    {...getRootProps()} 
                    className={`w-full border-2 border-dashed rounded-2xl p-10 text-center cursor-pointer transition-all duration-300
                      ${isDragActive ? 'border-blue-500 bg-blue-500/10 scale-[1.02]' : 'border-slate-700 hover:border-slate-500 hover:bg-slate-800/50'}
                    `}
                  >
                    <input {...getInputProps()} />
                    <UploadCloud className={`mx-auto h-12 w-12 mb-4 transition-colors ${isDragActive ? 'text-blue-400' : 'text-slate-500'}`} />
                    {file ? (
                      <div className="space-y-1">
                        <p className="text-lg font-semibold text-blue-300 truncate px-2">{file.name}</p>
                        <p className="text-sm text-slate-400">{(file.size / (1024 * 1024)).toFixed(2)} MB</p>
                      </div>
                    ) : (
                      <>
                        <p className="text-lg font-medium mb-1 text-slate-300">Drop your video here</p>
                        <p className="text-slate-500 text-sm">MP4, MOV, MKV format</p>
                      </>
                    )}
                  </div>
                </div>

                {/* Transcript Upload (Optional) */}
                <div className="mb-8">
                  <h3 className="text-lg font-semibold mb-4 flex items-center gap-2 text-slate-200">
                    <Type className="w-5 h-5 text-purple-400" /> Transcript (Optional)
                  </h3>
                  <div className="w-full border-2 border-dashed border-slate-700 hover:border-slate-500 hover:bg-slate-800/50 rounded-2xl p-6 text-center cursor-pointer transition-all duration-300 relative overflow-hidden">
                    <input 
                      type="file" 
                      accept=".json,.srt"
                      className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                      onChange={(e) => {
                        if (e.target.files && e.target.files.length > 0) {
                          setTranscriptFile(e.target.files[0]);
                        }
                      }}
                    />
                    {transcriptFile ? (
                      <div className="space-y-1">
                        <p className="text-md font-semibold text-purple-300 truncate px-2">{transcriptFile.name}</p>
                        <p className="text-xs text-slate-400">{(transcriptFile.size / 1024).toFixed(2)} KB</p>
                      </div>
                    ) : (
                      <>
                        <p className="text-md font-medium text-slate-300">Upload Transcript (.json or .srt)</p>
                        <p className="text-slate-500 text-xs mt-1">Speeds up generation by skipping Whisper AI</p>
                      </>
                    )}
                  </div>
                </div>

                {/* Generate Button */}
                <button
                  onClick={handleUpload}
                  disabled={!file || selectedDestinations.length === 0}
                  className={`w-full py-4 rounded-xl font-bold text-lg flex items-center justify-center gap-2 transition-all duration-300
                    ${file && selectedDestinations.length > 0
                      ? 'bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 hover:shadow-[0_0_30px_rgba(99,102,241,0.4)] hover:scale-[1.02] text-white' 
                      : 'bg-slate-800 text-slate-500 cursor-not-allowed border border-slate-700'}
                  `}
                >
                  <Scissors className="w-6 h-6" />
                  Generate AI Shorts
                </button>
                {error && (
                  <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-red-400 mt-4 text-center font-medium text-sm bg-red-400/10 py-2 rounded-lg border border-red-400/20">
                    {error}
                  </motion.p>
                )}
              </motion.div>
            )}

            {/* Status Panel */}
            {jobId && (
              <motion.div 
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="bg-slate-900/80 backdrop-blur-xl border border-indigo-500/30 rounded-3xl p-8 shadow-[0_0_40px_rgba(99,102,241,0.1)] relative overflow-hidden"
              >
                <div className="absolute top-0 left-0 w-full h-1 bg-slate-800">
                  <motion.div 
                    className="h-full bg-gradient-to-r from-blue-500 via-indigo-500 to-purple-500"
                    initial={{ width: 0 }}
                    animate={{ width: `${jobStatus?.progress || 0}%` }}
                    transition={{ ease: "linear" }}
                  />
                </div>
                
                <h3 className="text-2xl font-bold mb-8 text-center text-slate-100 flex items-center justify-center gap-3">
                  {jobStatus?.status === 'completed' ? (
                    <><CheckCircle className="text-green-400 w-8 h-8" /> Generation Complete</>
                  ) : jobStatus?.status === 'failed' ? (
                    <><span className="text-red-400">Generation Failed</span></>
                  ) : (
                    <><RefreshCw className="text-indigo-400 w-8 h-8 animate-spin" /> Processing Video...</>
                  )}
                </h3>

                <div className="space-y-6 relative">
                  <div className="flex justify-between items-center text-sm">
                    <span className="font-medium text-indigo-300">{jobStatus?.message || 'Initializing...'}</span>
                    <span className="font-bold text-slate-300 bg-slate-800 px-3 py-1 rounded-full">{jobStatus?.progress || 0}%</span>
                  </div>
                  
                  {jobStatus?.status !== 'completed' && jobStatus?.status !== 'failed' && (
                    <div className="mt-8 p-4 bg-slate-800/50 border border-slate-700 rounded-xl">
                      <p className="text-slate-400 text-sm flex items-center gap-2">
                        <Layers className="w-4 h-4" /> Extracting viral hooks, tracking faces, and burning styled captions...
                      </p>
                    </div>
                  )}
                </div>
              </motion.div>
            )}
          </div>

          {/* Right Column: Results Grid */}
          <div className="lg:col-span-7">
            {jobStatus?.status === 'completed' ? (
              <motion.div 
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                className="grid grid-cols-1 sm:grid-cols-2 gap-6"
              >
                <AnimatePresence>
                  {jobStatus.clips.map((clip, i) => {
                    // Bug #7 fix: extract destination from the LAST underscore segment
                    // before the extension (e.g. "My_Cool_Hook_tiktok.mp4" → "TIKTOK").
                    // Using a fixed index like [2] breaks when titles contain underscores.
                    const fileBasename = clip.split('/').pop() || clip;
                    const withoutExt = fileBasename.replace(/\.[^/.]+$/, '');
                    const segments = withoutExt.split('_');
                    const dest = segments.length > 0 ? segments[segments.length - 1].toUpperCase() : 'CLIP';
                    
                    return (
                      <motion.div 
                        key={i}
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: i * 0.15 }}
                        className="bg-slate-900/50 backdrop-blur-md rounded-2xl overflow-hidden border border-slate-800 shadow-xl group hover:border-indigo-500/50 transition-colors"
                      >
                        <div className="aspect-[9/16] bg-black flex items-center justify-center relative overflow-hidden">
                          <video 
                            src={`${BACKEND_URL}/${clip}`} 
                            className="w-full h-full object-contain"
                            controls
                            controlsList="nodownload"
                            poster=""
                          />
                          
                          {/* Top overlay badge */}
                          <div className="absolute top-4 left-4 pointer-events-none">
                            <span className="bg-black/60 backdrop-blur border border-white/10 text-white text-xs font-bold px-3 py-1.5 rounded-full shadow-lg">
                              {dest} FORMAT
                            </span>
                          </div>

                          {/* Hover Download Button */}
                          <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center pointer-events-none">
                            <a 
                              href={`${BACKEND_URL}/${clip}`} 
                              download 
                              className="pointer-events-auto bg-indigo-600 hover:bg-indigo-500 text-white p-4 rounded-full shadow-[0_0_20px_rgba(79,70,229,0.5)] transition-transform hover:scale-110"
                            >
                              <Download className="w-6 h-6" />
                            </a>
                          </div>
                        </div>
                        
                        <div className="p-5 bg-slate-900">
                          <h4 className="font-bold text-lg text-slate-200 mb-1">Generated Short #{i + 1}</h4>
                          <p className="text-sm text-slate-500">Optimized for {dest}</p>
                        </div>
                      </motion.div>
                    )
                  })}
                </AnimatePresence>
              </motion.div>
            ) : (
              <div className="h-full min-h-[400px] flex items-center justify-center border-2 border-dashed border-slate-800 rounded-3xl bg-slate-900/20">
                <div className="text-center p-8 max-w-sm">
                  <div className="w-20 h-20 bg-slate-800 rounded-full flex items-center justify-center mx-auto mb-6 shadow-inner">
                    <Video className="w-8 h-8 text-slate-600" />
                  </div>
                  <h3 className="text-xl font-bold text-slate-400 mb-2">No videos yet</h3>
                  <p className="text-slate-500 text-sm">Upload a video and select your target platforms to generate viral clips.</p>
                </div>
              </div>
            )}
          </div>

        </main>
      </div>
    </div>
  );
}

export default App;
