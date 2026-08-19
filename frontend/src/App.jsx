import React, { useState, useCallback, useEffect } from 'react';
import { useDropzone } from 'react-dropzone';
import { motion, AnimatePresence } from 'framer-motion';
import { UploadCloud, Video, Scissors, RefreshCw, Download, CheckCircle, Loader } from 'lucide-react';
import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';
const BACKEND_URL = API_URL.replace(/\/api$/, '');

function App() {
  const [file, setFile] = useState(null);
  const [jobId, setJobId] = useState(null);
  const [jobStatus, setJobStatus] = useState(null);
  const [error, setError] = useState('');

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
    
    const formData = new FormData();
    formData.append('file', file);
    
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
    <div className="container mx-auto px-4 py-12 max-w-5xl">
      <header className="text-center mb-12">
        <h1 className="text-5xl font-extrabold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-purple-500 mb-4 tracking-tight">
          Auto Shorts
        </h1>
        <p className="text-slate-400 text-lg">Local AI-Powered OpusClip Alternative</p>
      </header>

      <main className="glass-panel p-8">
        {!jobId && (
          <motion.div 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex flex-col items-center"
          >
            <div 
              {...getRootProps()} 
              className={`w-full border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-all duration-300
                ${isDragActive ? 'border-purple-500 bg-purple-500/10' : 'border-slate-600 hover:border-slate-400 hover:bg-slate-800/80'}
              `}
            >
              <input {...getInputProps()} />
              <UploadCloud className="mx-auto h-16 w-16 text-slate-400 mb-4" />
              {file ? (
                <p className="text-xl font-medium text-blue-300">{file.name}</p>
              ) : (
                <>
                  <p className="text-xl font-medium mb-2">Drag & drop your video here</p>
                  <p className="text-slate-400 text-sm">Supports MP4, MOV, MKV up to 4GB</p>
                </>
              )}
            </div>

            <button
              onClick={handleUpload}
              disabled={!file}
              className={`mt-8 px-8 py-3 rounded-full font-bold text-lg flex items-center gap-2 transition-all duration-300
                ${file 
                  ? 'bg-gradient-to-r from-blue-500 to-purple-600 hover:shadow-lg hover:shadow-purple-500/30' 
                  : 'bg-slate-700 text-slate-500 cursor-not-allowed'}
              `}
            >
              <Scissors className="w-5 h-5" />
              Generate Shorts
            </button>
            {error && <p className="text-red-400 mt-4">{error}</p>}
          </motion.div>
        )}

        {jobStatus && (
          <motion.div 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex flex-col items-center w-full"
          >
            <div className="w-full max-w-md">
              <div className="flex justify-between mb-2">
                <span className="text-sm font-medium text-slate-300">{jobStatus.message}</span>
                <span className="text-sm font-medium text-slate-300">{jobStatus.progress}%</span>
              </div>
              <div className="w-full bg-slate-700 rounded-full h-3 overflow-hidden">
                <motion.div 
                  className="bg-gradient-to-r from-blue-500 to-purple-500 h-3 rounded-full"
                  initial={{ width: 0 }}
                  animate={{ width: `${jobStatus.progress}%` }}
                />
              </div>
            </div>

            {jobStatus.status === 'completed' && (
              <div className="mt-12 w-full">
                <h3 className="text-2xl font-bold mb-6 flex items-center gap-2">
                  <CheckCircle className="text-green-400" /> 
                  Generated Shorts
                </h3>
                
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                  {jobStatus.clips.map((clip, i) => (
                    <motion.div 
                      key={i}
                      initial={{ opacity: 0, scale: 0.9 }}
                      animate={{ opacity: 1, scale: 1 }}
                      transition={{ delay: i * 0.1 }}
                      className="bg-slate-800 rounded-xl overflow-hidden border border-slate-700 shadow-lg"
                    >
                      <div className="aspect-[9/16] bg-black flex items-center justify-center relative group overflow-hidden">
                        <video 
                          src={`${BACKEND_URL}/${clip}`} 
                          className="w-full h-full object-cover"
                          controls
                          loop
                        />
                        <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity">
                          <a href={`${BACKEND_URL}/${clip}`} download className="bg-slate-800/80 p-2 rounded-full hover:bg-slate-700 transition-colors block border border-slate-600">
                            <Download className="w-5 h-5 text-white" />
                          </a>
                        </div>
                      </div>
                      <div className="p-4">
                        <h4 className="font-semibold text-lg truncate">Short #{i + 1}</h4>
                        <div className="flex justify-between items-center mt-4">
                          <button className="text-sm text-blue-400 hover:text-blue-300 flex items-center gap-1">
                            <RefreshCw className="w-4 h-4" /> Edit
                          </button>
                        </div>
                      </div>
                    </motion.div>
                  ))}
                </div>
              </div>
            )}
          </motion.div>
        )}
      </main>
    </div>
  );
}

export default App;
