import React, { useState, useCallback, useEffect } from 'react';
import { useDropzone } from 'react-dropzone';
import { motion, AnimatePresence } from 'framer-motion';
import {
  UploadCloud, Scissors, RefreshCw, Download, CheckCircle, Video,
  Type, Share2, Sparkles, Layers, Plus, Minus, RotateCcw, Film,
  Zap, Brain, MessageSquare, Copy, Check, ChevronDown, ChevronUp,
  Sliders, Hash, Compass, Lightbulb, Play, ExternalLink, X, Settings,
  AlertCircle, Send
} from 'lucide-react';
import axios from 'axios';

const API_URL     = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';
const BACKEND_URL = API_URL.replace(/\/api$/, '');

const AVAILABLE_FONTS = [
  { id: 'Montserrat-Black.ttf', name: 'Montserrat Black' },
  { id: 'Roboto-Black.ttf',     name: 'Roboto Black'     },
  { id: 'Super Bouncer.ttf',    name: 'Super Bouncer'    },
  { id: 'Helvetica Punk.ttf',   name: 'Helvetica Punk'   },
];

const DESTINATIONS = [
  { id: 'TikTok',    name: 'TikTok',         ratio: '9:16' },
  { id: 'YouTube',   name: 'YouTube Shorts', ratio: '9:16' },
  { id: 'Instagram', name: 'Instagram',      ratio: '1:1'  },
];

const CREATIVE_FOCUS_OPTIONS = [
  { id: 'curiosity', label: 'Curiosity & Mystery', icon: Compass, prompt: 'Prioritize moments with strong curiosity gaps, unanswered questions, shocking secrets, or counterintuitive premises.' },
  { id: 'humor',     label: 'High Energy & Humor', icon: Zap,     prompt: 'Prioritize high-energy punchlines, funny remarks, loud reactions, and emotional audio peaks.' },
  { id: 'wisdom',    label: 'Actionable Wisdom',  icon: Lightbulb, prompt: 'Prioritize clear actionable insights, tactical how-to advice, and life-changing frameworks.' },
  { id: 'custom',    label: 'Custom Directive',    icon: Sliders,  prompt: '' },
];

const clipPath  = (c) => (typeof c === 'string' ? c : c.path)  ?? '';
const clipTitle = (c) => (typeof c === 'string' ? null : c.title) ?? null;

function App() {
  // Form Inputs
  const [file,                 setFile]                 = useState(null);
  const [transcriptFile,       setTranscriptFile]       = useState(null);
  const [selectedFont,         setSelectedFont]         = useState(AVAILABLE_FONTS[0].id);
  const [selectedDestinations, setSelectedDestinations] = useState(['TikTok', 'YouTube']);
  const [numClips,             setNumClips]             = useState(3);
  const [creativeFocus,        setCreativeFocus]        = useState('curiosity');
  const [customDirectiveText,  setCustomDirectiveText]  = useState('');

  // Job & Processing States
  const [jobId,            setJobId]            = useState(null);
  const [jobStatus,        setJobStatus]        = useState(null);
  const [uploadProgress,   setUploadProgress]   = useState(0);
  const [error,            setError]            = useState('');
  const [editedCandidates, setEditedCandidates] = useState([]);
  const [isSubmittingRender, setIsSubmittingRender] = useState(false);

  // UI state
  const [copiedId,        setCopiedId]        = useState(null);
  const [expandedKit,     setExpandedKit]     = useState({});
  const [geminiInfo,      setGeminiInfo]      = useState({ available: true, model: 'gemini-3.7-flash' });

  // YouTube Channel Linking & Publishing State
  const [youtubeStatus, setYoutubeStatus] = useState({
    configured: false,
    connected: false,
    channel: null,
    client_id_preview: '',
    redirect_uri: 'http://localhost:8000/api/youtube/callback',
  });
  const [showYoutubeConfigModal, setShowYoutubeConfigModal] = useState(false);
  const [youtubeConfigForm, setYoutubeConfigForm] = useState({ clientId: '', clientSecret: '' });

  // Publishing Modal State
  const [publishingClip, setPublishingClip] = useState(null);
  const [publishForm, setPublishForm] = useState({
    title: '',
    description: '',
    tags: '',
    privacyStatus: 'public',
  });
  const [isPublishing, setIsPublishing] = useState(false);
  const [publishResult, setPublishResult] = useState(null);
  const [publishError, setPublishError] = useState('');

  // Fetch YouTube status
  const fetchYoutubeStatus = useCallback(() => {
    axios.get(`${API_URL}/youtube/status`)
      .then(res => {
        if (res.data) setYoutubeStatus(res.data);
      })
      .catch(err => console.error('Failed to fetch YouTube status:', err));
  }, []);

  // Listen for OAuth completion message from popup
  useEffect(() => {
    const handleMessage = (event) => {
      if (event.data?.type === 'YOUTUBE_AUTH_SUCCESS') {
        fetchYoutubeStatus();
        setShowYoutubeConfigModal(false);
      }
    };
    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [fetchYoutubeStatus]);

  // Fetch initial statuses on mount
  useEffect(() => {
    axios.get(`${API_URL}/gemini/status`)
      .then(res => {
        if (res.data) {
          setGeminiInfo({
            available: res.data.available,
            model: res.data.active_model || 'gemini-3.7-flash'
          });
        }
      })
      .catch(() => setGeminiInfo({ available: true, model: 'gemini-3.7-flash' }));

    fetchYoutubeStatus();
  }, [fetchYoutubeStatus]);

  // Destination toggle
  const toggleDestination = (id) =>
    setSelectedDestinations(prev =>
      prev.includes(id) ? prev.filter(d => d !== id) : [...prev, id]
    );

  // Dropzone
  const onDrop = useCallback(accepted => {
    if (accepted.length > 0) setFile(accepted[0]);
  }, []);
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'video/*': ['.mp4', '.mov', '.mkv'] },
    maxFiles: 1,
  });

  // Upload and start analysis
  const handleUpload = async () => {
    if (!file) return;
    if (selectedDestinations.length === 0) {
      setError('Please select at least one destination platform.');
      return;
    }

    const formData = new FormData();
    formData.append('file', file);
    if (transcriptFile) formData.append('transcript', transcriptFile);
    formData.append('font', selectedFont);
    formData.append('destinations', selectedDestinations.join(','));
    formData.append('num_clips', numClips);

    const focusConfig = CREATIVE_FOCUS_OPTIONS.find(f => f.id === creativeFocus);
    const directive = creativeFocus === 'custom' ? customDirectiveText : (focusConfig?.prompt || '');
    if (directive.trim()) {
      formData.append('custom_prompt', directive.trim());
    }

    try {
      setError('');
      setUploadProgress(0);
      const res = await axios.post(`${API_URL}/upload`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (evt) => {
          if (evt.total) setUploadProgress(Math.round((evt.loaded / evt.total) * 100));
        },
      });
      setJobId(res.data.job_id);
      setUploadProgress(100);
    } catch (err) {
      setError('Upload failed. Please check if the backend server is running.');
      setUploadProgress(0);
    }
  };

  // Polling for job status
  useEffect(() => {
    if (!jobId) return;

    const interval = setInterval(async () => {
      try {
        const res  = await axios.get(`${API_URL}/status/${jobId}`);
        const data = res.data;
        setJobStatus(data);

        // When entering review_ready for the first time, populate edited candidates
        if (data.status === 'review_ready' && data.metadata?.candidates) {
          setEditedCandidates(prev => {
            if (prev.length === 0) {
              return data.metadata.candidates.map(c => ({ ...c, selected: true }));
            }
            return prev;
          });
        }

        if (data.status === 'completed' || data.status === 'failed') {
          clearInterval(interval);
        }
      } catch (e) {
        console.error(e);
      }
    }, 1800);

    return () => clearInterval(interval);
  }, [jobId]);

  // Handle trimming updates in Review Studio
  const handleCandidateChange = (index, field, value) => {
    setEditedCandidates(prev => {
      const updated = [...prev];
      const item = { ...updated[index], [field]: value };
      if (field === 'start_time' || field === 'end_time') {
        const start = parseFloat(field === 'start_time' ? value : item.start_time) || 0;
        const end = parseFloat(field === 'end_time' ? value : item.end_time) || start + 30;
        item.duration = Math.max(1, Math.round((end - start) * 10) / 10);
      }
      updated[index] = item;
      return updated;
    });
  };

  // Trigger high-res rendering of selected trimmed clips
  const handleTriggerRender = async () => {
    if (!jobId || editedCandidates.length === 0) return;
    const selected = editedCandidates.filter(c => c.selected);
    if (selected.length === 0) {
      setError('Please select at least one clip to render.');
      return;
    }

    try {
      setIsSubmittingRender(true);
      setError('');
      await axios.post(`${API_URL}/render`, {
        job_id: jobId,
        clips: selected,
        font: selectedFont,
        destinations: selectedDestinations.join(','),
      });
    } catch (err) {
      setError('Failed to queue render. Please check the backend server.');
    } finally {
      setIsSubmittingRender(false);
    }
  };

  // Copy helper with animated checkmark
  const handleCopyText = (text, key) => {
    navigator.clipboard.writeText(text);
    setCopiedId(key);
    setTimeout(() => setCopiedId(null), 2200);
  };

  // Reset to create another video
  const handleReset = () => {
    setFile(null);
    setTranscriptFile(null);
    setJobId(null);
    setJobStatus(null);
    setUploadProgress(0);
    setEditedCandidates([]);
    setError('');
  };

  // Helper for category badges
  const getCategoryBadgeClass = (category) => {
    switch (category) {
      case 'Curiosity Gap':
        return 'bg-purple-500/20 text-purple-300 border-purple-500/40';
      case 'High Humor':
        return 'bg-amber-500/20 text-amber-300 border-amber-500/40';
      case 'Actionable Wisdom':
        return 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40';
      case 'Pattern Interrupt':
        return 'bg-rose-500/20 text-rose-300 border-rose-500/40';
      case 'Controversial Take':
        return 'bg-red-500/20 text-red-300 border-red-500/40';
      default:
        return 'bg-indigo-500/20 text-indigo-300 border-indigo-500/40';
    }
  };

  // ── YouTube Authentication Handlers ──
  const handleConnectYoutube = async () => {
    if (!youtubeStatus.configured) {
      setShowYoutubeConfigModal(true);
      return;
    }

    try {
      const res = await axios.get(`${API_URL}/youtube/auth-url`);
      if (res.data?.auth_url) {
        const width = 580;
        const height = 680;
        const left = window.screen.width / 2 - width / 2;
        const top = window.screen.height / 2 - height / 2;
        window.open(
          res.data.auth_url,
          'youtube_oauth_popup',
          `width=${width},height=${height},top=${top},left=${left}`
        );
      }
    } catch (err) {
      setShowYoutubeConfigModal(true);
    }
  };

  const handleSaveYoutubeConfig = async () => {
    if (!youtubeConfigForm.clientId || !youtubeConfigForm.clientSecret) return;
    try {
      await axios.post(`${API_URL}/youtube/configure`, {
        client_id: youtubeConfigForm.clientId.trim(),
        client_secret: youtubeConfigForm.clientSecret.trim(),
      });
      fetchYoutubeStatus();
      setShowYoutubeConfigModal(false);
      // Immediately open auth URL
      setTimeout(() => handleConnectYoutube(), 500);
    } catch (err) {
      alert('Failed to save credentials: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleDisconnectYoutube = async () => {
    if (!confirm('Unlink this YouTube channel from Auto Shorts?')) return;
    try {
      await axios.post(`${API_URL}/youtube/disconnect`);
      fetchYoutubeStatus();
    } catch (err) {
      console.error('Failed to unlink channel:', err);
    }
  };

  // ── YouTube 1-Click Publishing Handlers ──
  const handleOpenPublishModal = (clip) => {
    const rawTitle = clip.title || 'Viral Short';
    const formattedTitle = rawTitle.includes('#Shorts') ? rawTitle : `${rawTitle} #Shorts`;

    // Try finding matching candidate metadata for rich social kit
    const matchedCandidate = editedCandidates.find(c => c.title === clip.title || c.id === clip.id);
    const socialKit = matchedCandidate?.social_kit || clip.social_kit;

    const desc = socialKit?.caption
      ? `${socialKit.caption}\n\n${socialKit.hashtags?.join(' ') || ''}\n\n#Shorts #YouTubeShorts`
      : `Watch this high impact short!\n\n#Shorts #Viral`;

    const tagList = socialKit?.hashtags
      ? socialKit.hashtags.map(t => t.replace('#', '')).join(', ')
      : 'Shorts, Viral, Trending';

    setPublishForm({
      title: formattedTitle.slice(0, 100),
      description: desc,
      tags: tagList,
      privacyStatus: 'public',
    });
    setPublishingClip(clip);
    setPublishResult(null);
    setPublishError('');
  };

  const handlePublishToYoutube = async () => {
    if (!publishingClip) return;
    const clipP = clipPath(publishingClip) || publishingClip.preview_url || publishingClip.path;
    if (!clipP) {
      setPublishError('Could not find video file path.');
      return;
    }

    try {
      setIsPublishing(true);
      setPublishError('');
      const tagsArray = publishForm.tags.split(',').map(t => t.trim()).filter(Boolean);

      const res = await axios.post(`${API_URL}/youtube/publish`, {
        clip_path: clipP,
        title: publishForm.title,
        description: publishForm.description,
        tags: tagsArray,
        privacy_status: publishForm.privacyStatus,
        job_id: jobId || '',
      });

      setPublishResult(res.data);
    } catch (err) {
      setPublishError(err.response?.data?.detail || 'Failed to publish video to YouTube. Check backend logs.');
    } finally {
      setIsPublishing(false);
    }
  };

  const isReviewStage = jobStatus?.status === 'review_ready';
  const isRenderingStage = jobStatus?.status === 'rendering' || jobStatus?.status === 'queued_for_render';
  const isCompletedStage = jobStatus?.status === 'completed';

  return (
    <div className="min-h-screen bg-slate-950 text-white font-sans selection:bg-purple-500/30">

      {/* Dynamic Background Glows */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none z-0">
        <div className="absolute top-[-15%] left-[-10%] w-[55%] h-[55%] rounded-full bg-purple-600/15 blur-[140px]" />
        <div className="absolute top-[30%] right-[-15%] w-[50%] h-[50%] rounded-full bg-blue-600/10 blur-[150px]" />
        <div className="absolute bottom-[-10%] left-[20%] w-[45%] h-[45%] rounded-full bg-pink-600/10 blur-[140px]" />
      </div>

      <div className="container mx-auto px-6 py-12 max-w-7xl relative z-10">

        {/* ── Top Header & Integration Badges ── */}
        <header className="text-center mb-12">
          <div className="flex flex-wrap items-center justify-center gap-3.5 mb-5">
            {/* Gemini Status Badge */}
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1,   opacity: 1 }}
              transition={{ duration: 0.5 }}
              className="inline-flex items-center gap-2.5 px-4 py-1.5 rounded-full bg-slate-900/80 border border-purple-500/30 backdrop-blur-md shadow-[0_0_20px_rgba(168,85,247,0.15)]"
            >
              <Sparkles className="w-4 h-4 text-purple-400 animate-pulse" />
              <span className="text-xs sm:text-sm font-semibold tracking-wide bg-clip-text text-transparent bg-gradient-to-r from-purple-300 via-pink-300 to-indigo-300">
                Google Gemini 3.7 Flash Active
              </span>
              <span className="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_8px_#34d399]" />
            </motion.div>

            {/* YouTube Channel Badge / Connect Button */}
            {youtubeStatus.connected && youtubeStatus.channel ? (
              <motion.div
                initial={{ scale: 0.9, opacity: 0 }}
                animate={{ scale: 1,   opacity: 1 }}
                className="inline-flex items-center gap-2.5 px-4 py-1.5 rounded-full bg-slate-900/80 border border-red-500/40 backdrop-blur-md shadow-[0_0_20px_rgba(239,68,68,0.15)]"
              >
                {youtubeStatus.channel.avatar ? (
                  <img
                    src={youtubeStatus.channel.avatar}
                    alt={youtubeStatus.channel.title}
                    className="w-5 h-5 rounded-full border border-red-400 object-cover"
                  />
                ) : (
                  <Video className="w-4 h-4 text-red-500" />
                )}
                <span className="text-xs sm:text-sm font-bold text-slate-200">
                  {youtubeStatus.channel.title}
                </span>
                <button
                  onClick={handleDisconnectYoutube}
                  title="Unlink YouTube Channel"
                  className="text-slate-400 hover:text-red-400 ml-1 transition-colors cursor-pointer"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </motion.div>
            ) : (
              <motion.button
                initial={{ scale: 0.9, opacity: 0 }}
                animate={{ scale: 1,   opacity: 1 }}
                onClick={handleConnectYoutube}
                className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-red-600/20 hover:bg-red-600/30 border border-red-500/40 text-red-300 hover:text-white transition-all text-xs sm:text-sm font-bold shadow-[0_0_20px_rgba(239,68,68,0.15)] cursor-pointer"
              >
                <Video className="w-4 h-4 text-red-500" />
                <span>Link YouTube Channel</span>
              </motion.button>
            )}

            {/* YouTube Settings Gear Button */}
            <motion.button
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1,   opacity: 1 }}
              onClick={() => setShowYoutubeConfigModal(true)}
              title="YouTube OAuth Credentials Settings"
              className="p-2 rounded-full bg-slate-900/80 hover:bg-slate-800 border border-slate-700/80 text-slate-400 hover:text-white transition-all cursor-pointer"
            >
              <Settings className="w-4 h-4" />
            </motion.button>
          </div>

          <h1 className="text-5xl sm:text-6xl font-black mb-4 tracking-tight leading-tight">
            Auto <span className="bg-clip-text text-transparent bg-gradient-to-r from-blue-400 via-indigo-500 to-purple-500">Shorts</span>
          </h1>
          <p className="text-slate-400 text-lg sm:text-xl max-w-2xl mx-auto leading-relaxed">
            Multi-modal viral hook detection powered by Gemini Chain-of-Thought AI, RMS audio energy profiling, and 1-click publishing to YouTube Shorts.
          </p>
        </header>

        {/* ── STAGE 1: UPLOAD & CONFIGURATION FORM ── */}
        {!jobId && (
          <main className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
            <div className="lg:col-span-7 space-y-6">
              <motion.div
                initial={{ opacity: 0, y: 15 }}
                animate={{ opacity: 1, y: 0 }}
                className="bg-slate-900/60 backdrop-blur-xl border border-slate-800/80 rounded-3xl p-8 shadow-2xl space-y-8"
              >
                {/* Video Dropzone */}
                <div>
                  <h3 className="text-lg font-semibold mb-3 flex items-center gap-2 text-slate-200">
                    <Video className="w-5 h-5 text-blue-400" /> Source Video
                  </h3>
                  <div
                    {...getRootProps()}
                    className={`w-full border-2 border-dashed rounded-2xl p-10 text-center cursor-pointer transition-all duration-300 ${
                      isDragActive
                        ? 'border-blue-500 bg-blue-500/10 scale-[1.01]'
                        : 'border-slate-700/80 hover:border-slate-500 hover:bg-slate-800/40'
                    }`}
                  >
                    <input {...getInputProps()} />
                    <UploadCloud className={`mx-auto h-12 w-12 mb-3 transition-colors ${isDragActive ? 'text-blue-400' : 'text-slate-500'}`} />
                    {file ? (
                      <div className="space-y-1">
                        <p className="text-lg font-bold text-blue-300 truncate px-4">{file.name}</p>
                        <p className="text-sm text-slate-400 font-mono">{(file.size / (1024 * 1024)).toFixed(2)} MB</p>
                      </div>
                    ) : (
                      <>
                        <p className="text-lg font-medium text-slate-300">Drag & drop your video here</p>
                        <p className="text-slate-500 text-sm mt-1">Supports MP4, MOV, MKV up to 4K</p>
                      </>
                    )}
                  </div>
                </div>

                {/* Gemini AI Creative Focus */}
                <div>
                  <h3 className="text-lg font-semibold mb-3 flex items-center gap-2 text-slate-200">
                    <Brain className="w-5 h-5 text-purple-400" /> AI Creative Focus (Gemini 3.7 Flash)
                  </h3>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
                    {CREATIVE_FOCUS_OPTIONS.map(opt => {
                      const Icon = opt.icon;
                      const isSelected = creativeFocus === opt.id;
                      return (
                        <button
                          key={opt.id}
                          type="button"
                          onClick={() => setCreativeFocus(opt.id)}
                          className={`flex items-center gap-3 p-3.5 rounded-xl border text-left transition-all duration-200 ${
                            isSelected
                              ? 'bg-purple-500/15 border-purple-500 text-white shadow-[0_0_15px_rgba(168,85,247,0.2)]'
                              : 'bg-slate-800/40 border-slate-700/70 text-slate-400 hover:bg-slate-800 hover:border-slate-600'
                          }`}
                        >
                          <Icon className={`w-5 h-5 ${isSelected ? 'text-purple-400' : 'text-slate-500'}`} />
                          <span className="text-sm font-semibold">{opt.label}</span>
                        </button>
                      );
                    })}
                  </div>

                  {creativeFocus === 'custom' && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      className="mt-3"
                    >
                      <input
                        type="text"
                        placeholder="e.g. Focus on high-retention trading lessons and avoid intro chatter..."
                        value={customDirectiveText}
                        onChange={(e) => setCustomDirectiveText(e.target.value)}
                        className="w-full bg-slate-950 border border-purple-500/40 rounded-xl px-4 py-3 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:ring-2 focus:ring-purple-500/40"
                      />
                    </motion.div>
                  )}
                </div>

                {/* Optional Transcript */}
                <div>
                  <h3 className="text-lg font-semibold mb-3 flex items-center gap-2 text-slate-200">
                    <Type className="w-5 h-5 text-indigo-400" /> Transcript (Optional)
                  </h3>
                  <div className="w-full border-2 border-dashed border-slate-700/80 hover:border-slate-500 hover:bg-slate-800/40 rounded-2xl p-5 text-center cursor-pointer transition-all duration-300 relative overflow-hidden">
                    <input
                      type="file"
                      accept=".json,.srt"
                      className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                      onChange={e => { if (e.target.files?.length > 0) setTranscriptFile(e.target.files[0]); }}
                    />
                    {transcriptFile ? (
                      <div>
                        <p className="text-md font-semibold text-indigo-300 truncate px-2">{transcriptFile.name}</p>
                        <p className="text-xs text-slate-400 font-mono">{(transcriptFile.size / 1024).toFixed(2)} KB</p>
                      </div>
                    ) : (
                      <>
                        <p className="text-sm font-medium text-slate-300">Upload Transcript (.json or .srt)</p>
                        <p className="text-slate-500 text-xs mt-0.5">Optional — skips Whisper AI transcription for instant processing</p>
                      </>
                    )}
                  </div>
                </div>

                {/* Analyze Button */}
                <button
                  onClick={handleUpload}
                  disabled={!file || selectedDestinations.length === 0}
                  className={`w-full py-4 rounded-xl font-bold text-lg flex items-center justify-center gap-3 transition-all duration-300 ${
                    file && selectedDestinations.length > 0
                      ? 'bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 hover:shadow-[0_0_35px_rgba(99,102,241,0.45)] hover:scale-[1.01] text-white cursor-pointer'
                      : 'bg-slate-800/80 text-slate-600 cursor-not-allowed border border-slate-800'
                  }`}
                >
                  <Sparkles className="w-6 h-6 text-purple-200" />
                  Detect Viral Hooks with Gemini
                </button>

                {error && (
                  <motion.p
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="text-red-400 text-center font-medium text-sm bg-red-400/10 py-2.5 px-4 rounded-xl border border-red-400/20"
                  >
                    {error}
                  </motion.p>
                )}
              </motion.div>
            </div>

            {/* Right Column: Settings & Highlights */}
            <div className="lg:col-span-5 space-y-6">
              <div className="bg-slate-900/60 backdrop-blur-xl border border-slate-800/80 rounded-3xl p-8 shadow-2xl space-y-7">
                {/* Number of Clips */}
                <div>
                  <h3 className="text-lg font-semibold mb-3 flex items-center gap-2 text-slate-200">
                    <Film className="w-5 h-5 text-yellow-400" /> Viral Hooks to Extract
                  </h3>
                  <div className="flex items-center gap-4 bg-slate-950/60 p-3 rounded-2xl border border-slate-800">
                    <button
                      onClick={() => setNumClips(n => Math.max(1, n - 1))}
                      disabled={numClips <= 1}
                      className="w-10 h-10 rounded-xl bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-300 hover:bg-slate-700 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
                    >
                      <Minus className="w-4 h-4" />
                    </button>
                    <span className="text-3xl font-black text-white w-8 text-center">{numClips}</span>
                    <button
                      onClick={() => setNumClips(n => Math.min(5, n + 1))}
                      disabled={numClips >= 5}
                      className="w-10 h-10 rounded-xl bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-300 hover:bg-slate-700 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
                    >
                      <Plus className="w-4 h-4" />
                    </button>
                    <span className="text-slate-400 text-sm ml-2">Self-contained clips (30s–90s)</span>
                  </div>
                </div>

                {/* Target Platforms */}
                <div>
                  <h3 className="text-lg font-semibold mb-3 flex items-center gap-2 text-slate-200">
                    <Share2 className="w-5 h-5 text-pink-400" /> Target Platforms
                  </h3>
                  <div className="flex flex-col gap-2.5">
                    {DESTINATIONS.map(dest => (
                      <button
                        key={dest.id}
                        onClick={() => toggleDestination(dest.id)}
                        className={`flex items-center justify-between px-4 py-3.5 rounded-xl border transition-all duration-200 ${
                          selectedDestinations.includes(dest.id)
                            ? 'bg-pink-500/10 border-pink-500/60 shadow-[0_0_15px_rgba(236,72,153,0.15)] text-white'
                            : 'bg-slate-800/40 border-slate-700/60 text-slate-400 hover:bg-slate-800'
                        }`}
                      >
                        <div className="flex items-center gap-3">
                          <div className={`w-5 h-5 rounded-md flex items-center justify-center border ${
                            selectedDestinations.includes(dest.id) ? 'bg-pink-500 border-pink-500' : 'border-slate-600 bg-slate-900'
                          }`}>
                            {selectedDestinations.includes(dest.id) && <Check className="w-3.5 h-3.5 text-white" />}
                          </div>
                          <span className="font-semibold text-sm">{dest.name}</span>
                        </div>
                        <span className="text-xs font-mono text-slate-400 bg-slate-900 px-2 py-1 rounded-md border border-slate-800">
                          {dest.ratio}
                        </span>
                      </button>
                    ))}
                  </div>
                </div>

                {/* Subtitle Font */}
                <div>
                  <h3 className="text-lg font-semibold mb-3 flex items-center gap-2 text-slate-200">
                    <Type className="w-5 h-5 text-indigo-400" /> Dynamic Caption Font
                  </h3>
                  <div className="grid grid-cols-2 gap-2.5">
                    {AVAILABLE_FONTS.map(font => (
                      <button
                        key={font.id}
                        onClick={() => setSelectedFont(font.id)}
                        className={`px-3 py-2.5 rounded-xl border text-xs font-semibold transition-all duration-200 ${
                          selectedFont === font.id
                            ? 'bg-indigo-500/20 border-indigo-500 text-indigo-300 shadow-[0_0_15px_rgba(99,102,241,0.2)]'
                            : 'bg-slate-800/40 border-slate-700/60 text-slate-400 hover:bg-slate-800'
                        }`}
                      >
                        {font.name}
                      </button>
                    ))}
                  </div>
                  <p className="text-xs text-slate-500 mt-2 flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5 text-yellow-400" />
                    Gemini power words pop automatically in neon yellow (<span className="text-yellow-300 font-mono">#FFE600</span>).
                  </p>
                </div>
              </div>
            </div>
          </main>
        )}

        {/* ── STAGE 2: PROCESSING & ANALYSIS SPINNER ── */}
        {jobId && !isReviewStage && !isRenderingStage && !isCompletedStage && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="max-w-2xl mx-auto bg-slate-900/80 backdrop-blur-xl border border-indigo-500/30 rounded-3xl p-10 shadow-[0_0_50px_rgba(99,102,241,0.15)] relative overflow-hidden text-center"
          >
            <div className="absolute top-0 left-0 w-full h-1.5 bg-slate-800">
              <motion.div
                className="h-full bg-gradient-to-r from-blue-500 via-indigo-500 to-purple-500"
                initial={{ width: 0 }}
                animate={{ width: `${jobStatus?.progress || uploadProgress || 10}%` }}
                transition={{ ease: 'linear' }}
              />
            </div>

            <RefreshCw className="w-12 h-12 text-indigo-400 animate-spin mx-auto mb-6" />

            <h3 className="text-2xl font-black text-slate-100 mb-2">
              Gemini AI Multi-Modal Engine
            </h3>
            <p className="text-indigo-300 font-medium text-sm mb-6">
              {uploadProgress < 100 && !jobStatus
                ? `Uploading video file (${uploadProgress}%)...`
                : jobStatus?.message || 'Analyzing vocal energy and detecting viral hooks...'}
            </p>

            <div className="space-y-3 max-w-md mx-auto text-left text-xs text-slate-400 bg-slate-950/60 p-5 rounded-2xl border border-slate-800/80">
              <div className="flex items-center gap-2">
                <CheckCircle className="w-4 h-4 text-emerald-400" />
                <span>Audio extraction & RMS energy spike detection</span>
              </div>
              <div className="flex items-center gap-2">
                <CheckCircle className="w-4 h-4 text-emerald-400" />
                <span>Whisper word-level timestamp transcription</span>
              </div>
              <div className="flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-purple-400 animate-pulse" />
                <span>Gemini 3.7 Flash Chain-of-Thought hook scoring</span>
              </div>
              <div className="flex items-center gap-2">
                <Play className="w-4 h-4 text-blue-400" />
                <span>Generating instant 360p in-browser preview cuts</span>
              </div>
            </div>
          </motion.div>
        )}

        {/* ── STAGE 3: INTERACTIVE REVIEW & TRIMMING STUDIO ── */}
        {isReviewStage && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="space-y-8"
          >
            {/* Studio Header Bar */}
            <div className="bg-slate-900/80 backdrop-blur-xl border border-indigo-500/40 rounded-3xl p-6 sm:p-8 flex flex-col md:flex-row items-start md:items-center justify-between gap-6 shadow-[0_0_40px_rgba(99,102,241,0.12)]">
              <div>
                <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-purple-500/20 text-purple-300 border border-purple-500/30 text-xs font-semibold mb-2">
                  <Sparkles className="w-3.5 h-3.5" /> Stage 2: Fine-Tuning Studio
                </div>
                <h2 className="text-2xl sm:text-3xl font-black text-white">
                  Gemini Identified {editedCandidates.length} Viral Segments
                </h2>
                <p className="text-slate-400 text-sm mt-1">
                  Preview 360p cuts, fine-tune timestamps, explore AI virality metrics, and publish directly to YouTube Shorts.
                </p>
              </div>

              {/* Render Action Button */}
              <div className="flex items-center gap-4 w-full md:w-auto">
                <button
                  onClick={handleTriggerRender}
                  disabled={isSubmittingRender || editedCandidates.filter(c => c.selected).length === 0}
                  className="w-full md:w-auto px-8 py-4 rounded-2xl font-black text-base flex items-center justify-center gap-3 bg-gradient-to-r from-pink-500 via-purple-600 to-indigo-600 hover:shadow-[0_0_35px_rgba(236,72,153,0.4)] hover:scale-[1.02] text-white transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <Scissors className="w-5 h-5" />
                  Render Selected ({editedCandidates.filter(c => c.selected).length}) Shorts
                </button>
              </div>
            </div>

            {/* Candidate Hooks Grid */}
            <div className="grid grid-cols-1 gap-8">
              {editedCandidates.map((candidate, idx) => {
                const isSelected = candidate.selected;
                const isKitOpen = !!expandedKit[candidate.id];

                return (
                  <motion.div
                    key={candidate.id || idx}
                    layout
                    className={`bg-slate-900/60 backdrop-blur-xl border rounded-3xl overflow-hidden transition-all duration-300 ${
                      isSelected
                        ? 'border-indigo-500/60 shadow-[0_0_30px_rgba(99,102,241,0.15)]'
                        : 'border-slate-800 opacity-60'
                    }`}
                  >
                    {/* Card Header Bar */}
                    <div className="p-5 sm:p-6 bg-slate-900/90 border-b border-slate-800 flex flex-wrap items-center justify-between gap-4">
                      <div className="flex items-center gap-3 flex-1 min-w-[240px]">
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={(e) => handleCandidateChange(idx, 'selected', e.target.checked)}
                          className="w-5 h-5 accent-indigo-600 rounded cursor-pointer"
                        />

                        <input
                          type="text"
                          value={candidate.title}
                          onChange={(e) => handleCandidateChange(idx, 'title', e.target.value)}
                          className="bg-transparent border-b border-dashed border-slate-600 hover:border-indigo-400 focus:border-indigo-400 focus:outline-none text-lg sm:text-xl font-bold text-white flex-1 truncate"
                        />
                      </div>

                      <div className="flex items-center gap-3">
                        <span className={`px-3 py-1 rounded-full text-xs font-bold border ${getCategoryBadgeClass(candidate.hook_category)}`}>
                          {candidate.hook_category || 'Curiosity Gap'}
                        </span>
                        <span className="text-xs font-mono bg-slate-800 px-3 py-1 rounded-full text-slate-300 border border-slate-700">
                          {candidate.duration}s
                        </span>
                      </div>
                    </div>

                    {/* Card Body */}
                    <div className="p-6 sm:p-8 grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
                      {/* Left: 360p Preview Player */}
                      <div className="lg:col-span-4">
                        <div className="aspect-[9/16] bg-black rounded-2xl overflow-hidden relative shadow-2xl border border-slate-800">
                          {candidate.preview_url ? (
                            <video
                              src={`${BACKEND_URL}/${candidate.preview_url}`}
                              controls
                              playsInline
                              className="w-full h-full object-contain"
                            />
                          ) : (
                            <div className="w-full h-full flex flex-col items-center justify-center p-6 text-center text-slate-500">
                              <Video className="w-10 h-10 mb-2" />
                              <p className="text-xs">Fast 360p preview rendering...</p>
                            </div>
                          )}

                          <div className="absolute top-3 left-3 pointer-events-none">
                            <span className="bg-black/70 backdrop-blur text-[10px] font-bold text-slate-200 px-2.5 py-1 rounded-full border border-white/10">
                              360P PREVIEW
                            </span>
                          </div>
                        </div>
                      </div>

                      {/* Right: Virality Metrics & Trimmer & Social Kit */}
                      <div className="lg:col-span-8 space-y-6">
                        {/* 4 Virality Metrics */}
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                          <div className="bg-slate-950/70 p-3.5 rounded-2xl border border-slate-800/80 text-center">
                            <span className="text-[10px] uppercase font-bold text-indigo-400 tracking-wider">Overall Virality</span>
                            <p className="text-2xl font-black text-white mt-1">{candidate.engagement_score || 8.5}<span className="text-xs text-slate-500">/10</span></p>
                          </div>
                          <div className="bg-slate-950/70 p-3.5 rounded-2xl border border-slate-800/80 text-center">
                            <span className="text-[10px] uppercase font-bold text-purple-400 tracking-wider">Retention Score</span>
                            <p className="text-2xl font-black text-white mt-1">{candidate.retention_score || 8.2}<span className="text-xs text-slate-500">/10</span></p>
                          </div>
                          <div className="bg-slate-950/70 p-3.5 rounded-2xl border border-slate-800/80 text-center">
                            <span className="text-[10px] uppercase font-bold text-pink-400 tracking-wider">Emotion Score</span>
                            <p className="text-2xl font-black text-white mt-1">{candidate.emotion_score || 8.0}<span className="text-xs text-slate-500">/10</span></p>
                          </div>
                          <div className="bg-slate-950/70 p-3.5 rounded-2xl border border-slate-800/80 text-center">
                            <span className="text-[10px] uppercase font-bold text-amber-400 tracking-wider">Audio Energy Spike</span>
                            <p className="text-2xl font-black text-white mt-1">{candidate.energy_score || 85}%</p>
                          </div>
                        </div>

                        {/* CoT Reasoning & Creator Tip */}
                        <div className="bg-slate-950/60 p-5 rounded-2xl border border-slate-800/80 space-y-3 text-sm">
                          <div>
                            <span className="text-xs font-bold text-purple-300 flex items-center gap-1.5 mb-1">
                              <Brain className="w-3.5 h-3.5" /> Why this works (Gemini CoT):
                            </span>
                            <p className="text-slate-300 leading-relaxed text-xs sm:text-sm">
                              {candidate.reason}
                            </p>
                          </div>

                          {candidate.virality_tip && (
                            <div className="pt-2 border-t border-slate-800/80">
                              <span className="text-xs font-bold text-yellow-300 flex items-center gap-1.5 mb-1">
                                <Lightbulb className="w-3.5 h-3.5" /> Creator Optimization Tip:
                              </span>
                              <p className="text-slate-400 text-xs sm:text-sm">
                                {candidate.virality_tip}
                              </p>
                            </div>
                          )}
                        </div>

                        {/* Highlighted Power Words in Neon */}
                        {candidate.highlight_words && candidate.highlight_words.length > 0 && (
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-xs text-slate-400 flex items-center gap-1">
                              <Sparkles className="w-3.5 h-3.5 text-yellow-400" /> Power Words:
                            </span>
                            {candidate.highlight_words.map((word, wIdx) => (
                              <span
                                key={wIdx}
                                className="px-2.5 py-0.5 rounded-md text-xs font-black bg-yellow-400/15 text-yellow-300 border border-yellow-400/40 uppercase tracking-wide"
                              >
                                {word}
                              </span>
                            ))}
                            <span className="text-[11px] text-slate-500 italic ml-1">
                              (Highlighted in neon yellow captions)
                            </span>
                          </div>
                        )}

                        {/* Timestamp Trimmer Controls */}
                        <div className="bg-slate-950/60 p-4 rounded-2xl border border-slate-800/80 flex flex-wrap items-center justify-between gap-4">
                          <div className="flex items-center gap-3">
                            <Sliders className="w-4 h-4 text-indigo-400" />
                            <span className="text-xs font-bold text-slate-300">Fine-Tune Trim:</span>
                          </div>

                          <div className="flex items-center gap-6">
                            {/* Start Time */}
                            <div className="flex items-center gap-2">
                              <span className="text-xs text-slate-400">Start (s):</span>
                              <input
                                type="number"
                                step="0.5"
                                min="0"
                                value={candidate.start_time}
                                onChange={(e) => handleCandidateChange(idx, 'start_time', e.target.value)}
                                className="w-20 bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1 text-sm font-mono text-center focus:outline-none focus:border-indigo-500"
                              />
                            </div>

                            {/* End Time */}
                            <div className="flex items-center gap-2">
                              <span className="text-xs text-slate-400">End (s):</span>
                              <input
                                type="number"
                                step="0.5"
                                min={candidate.start_time + 5}
                                value={candidate.end_time}
                                onChange={(e) => handleCandidateChange(idx, 'end_time', e.target.value)}
                                className="w-20 bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1 text-sm font-mono text-center focus:outline-none focus:border-indigo-500"
                              />
                            </div>
                          </div>
                        </div>

                        {/* Social Media Kit Accordion & Direct YouTube Button */}
                        {candidate.social_kit && (
                          <div className="border border-slate-800 rounded-2xl overflow-hidden bg-slate-950/40">
                            <button
                              onClick={() => setExpandedKit(p => ({ ...p, [candidate.id]: !p[candidate.id] }))}
                              className="w-full px-5 py-3.5 flex items-center justify-between text-left hover:bg-slate-900/50 transition-colors"
                            >
                              <div className="flex items-center gap-2.5 text-sm font-bold text-slate-200">
                                <Share2 className="w-4 h-4 text-pink-400" />
                                <span>AI Social Media Kit (TikTok / Reels / Shorts)</span>
                              </div>
                              {isKitOpen ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
                            </button>

                            {isKitOpen && (
                              <motion.div
                                initial={{ opacity: 0, height: 0 }}
                                animate={{ opacity: 1, height: 'auto' }}
                                className="p-5 border-t border-slate-800/80 space-y-4 text-xs"
                              >
                                {/* Social Headline */}
                                <div>
                                  <div className="flex justify-between items-center mb-1">
                                    <span className="font-bold text-slate-400 uppercase tracking-wider">Post Headline:</span>
                                    <button
                                      onClick={() => handleCopyText(candidate.social_kit.headline, `${candidate.id}_headline`)}
                                      className="text-indigo-400 hover:text-indigo-300 flex items-center gap-1 font-semibold"
                                    >
                                      {copiedId === `${candidate.id}_headline` ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                                      {copiedId === `${candidate.id}_headline` ? 'Copied' : 'Copy'}
                                    </button>
                                  </div>
                                  <p className="p-3 bg-slate-900 rounded-xl text-slate-200 font-medium">
                                    {candidate.social_kit.headline}
                                  </p>
                                </div>

                                {/* Caption */}
                                <div>
                                  <div className="flex justify-between items-center mb-1">
                                    <span className="font-bold text-slate-400 uppercase tracking-wider">Caption + Call-To-Action:</span>
                                    <button
                                      onClick={() => handleCopyText(candidate.social_kit.caption, `${candidate.id}_caption`)}
                                      className="text-indigo-400 hover:text-indigo-300 flex items-center gap-1 font-semibold"
                                    >
                                      {copiedId === `${candidate.id}_caption` ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                                      {copiedId === `${candidate.id}_caption` ? 'Copied' : 'Copy'}
                                    </button>
                                  </div>
                                  <p className="p-3 bg-slate-900 rounded-xl text-slate-300 leading-relaxed whitespace-pre-wrap">
                                    {candidate.social_kit.caption}
                                  </p>
                                </div>

                                {/* Hashtags */}
                                <div>
                                  <div className="flex justify-between items-center mb-1">
                                    <span className="font-bold text-slate-400 uppercase tracking-wider">Hashtags:</span>
                                    <button
                                      onClick={() => handleCopyText(candidate.social_kit.hashtags?.join(' ') || '', `${candidate.id}_tags`)}
                                      className="text-indigo-400 hover:text-indigo-300 flex items-center gap-1 font-semibold"
                                    >
                                      {copiedId === `${candidate.id}_tags` ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                                      {copiedId === `${candidate.id}_tags` ? 'Copied All' : 'Copy All'}
                                    </button>
                                  </div>
                                  <p className="p-3 bg-slate-900 rounded-xl text-pink-400 font-mono">
                                    {candidate.social_kit.hashtags?.join(' ')}
                                  </p>
                                </div>
                              </motion.div>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  </motion.div>
                );
              })}
            </div>
          </motion.div>
        )}

        {/* ── STAGE 4: RENDERING HIGH-RES PROGRESS ── */}
        {isRenderingStage && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="max-w-2xl mx-auto bg-slate-900/80 backdrop-blur-xl border border-purple-500/30 rounded-3xl p-10 shadow-[0_0_50px_rgba(168,85,247,0.15)] relative overflow-hidden text-center"
          >
            <div className="absolute top-0 left-0 w-full h-1.5 bg-slate-800">
              <motion.div
                className="h-full bg-gradient-to-r from-pink-500 via-purple-500 to-indigo-500"
                initial={{ width: '70%' }}
                animate={{ width: `${jobStatus?.progress || 75}%` }}
                transition={{ ease: 'linear' }}
              />
            </div>

            <Scissors className="w-12 h-12 text-pink-400 animate-bounce mx-auto mb-6" />

            <h3 className="text-2xl font-black text-white mb-2">
              Rendering High-Resolution Shorts
            </h3>
            <p className="text-purple-300 font-medium text-sm mb-6">
              {jobStatus?.message || 'Burning karaoke subtitles with neon power words & blurring cinematic canvas...'}
            </p>

            <div className="space-y-2 max-w-sm mx-auto text-left text-xs text-slate-400 bg-slate-950/60 p-4 rounded-xl border border-slate-800">
              <div className="flex items-center gap-2">
                <CheckCircle className="w-4 h-4 text-emerald-400" />
                <span>Face-centered background crop</span>
              </div>
              <div className="flex items-center gap-2">
                <CheckCircle className="w-4 h-4 text-emerald-400" />
                <span>Word-level neon karaoke subtitles</span>
              </div>
              <div className="flex items-center gap-2">
                <RefreshCw className="w-4 h-4 text-purple-400 animate-spin" />
                <span>Multi-platform aspect ratios (9:16 & 1:1)</span>
              </div>
            </div>
          </motion.div>
        )}

        {/* ── STAGE 5: COMPLETED FINAL SHORTS DISPLAY ── */}
        {isCompletedStage && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="space-y-8"
          >
            {/* Completed Banner */}
            <div className="bg-slate-900/80 backdrop-blur-xl border border-emerald-500/30 rounded-3xl p-6 sm:p-8 flex flex-col md:flex-row items-start md:items-center justify-between gap-4 shadow-[0_0_40px_rgba(16,185,129,0.1)]">
              <div>
                <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 text-xs font-semibold mb-2">
                  <CheckCircle className="w-3.5 h-3.5" /> Production Complete
                </div>
                <h2 className="text-2xl sm:text-3xl font-black text-white">
                  Your Shorts Are Ready to Publish!
                </h2>
                <p className="text-slate-400 text-sm mt-1">
                  High-definition shorts formatted with burned karaoke captions. Post directly to your linked YouTube channel with 1-click.
                </p>
              </div>

              <button
                onClick={handleReset}
                className="px-6 py-3 rounded-xl font-bold text-sm flex items-center justify-center gap-2 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 transition-all cursor-pointer"
              >
                <RotateCcw className="w-4 h-4" />
                Create Another Short
              </button>
            </div>

            {/* Video Cards Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
              {jobStatus.clips.map((clip, i) => {
                const path = clipPath(clip);
                const title = clipTitle(clip);
                const basename = path.split('/').pop() || path;
                const withoutExt = basename.replace(/\.[^/.]+$/, '');
                const segments = withoutExt.split('_');
                const dest = segments.length > 0 ? segments[segments.length - 1].toUpperCase() : 'SHORT';

                return (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.1 }}
                    className="bg-slate-900/60 backdrop-blur-md rounded-3xl overflow-hidden border border-slate-800 shadow-xl group hover:border-indigo-500/50 transition-all flex flex-col"
                  >
                    <div className="aspect-[9/16] bg-black flex items-center justify-center relative overflow-hidden">
                      <video
                        src={`${BACKEND_URL}/${path}`}
                        className="w-full h-full object-contain"
                        controls
                        controlsList="nodownload"
                      />

                      {/* Format Badge */}
                      <div className="absolute top-4 left-4 pointer-events-none">
                        <span className="bg-black/70 backdrop-blur border border-white/15 text-white text-[11px] font-black px-3 py-1.5 rounded-full shadow-lg">
                          {dest}
                        </span>
                      </div>

                      {/* Download Overlay */}
                      <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center pointer-events-none">
                        <a
                          href={`${BACKEND_URL}/${path}`}
                          download
                          className="pointer-events-auto bg-indigo-600 hover:bg-indigo-500 text-white p-4 rounded-full shadow-[0_0_25px_rgba(79,70,229,0.5)] transition-transform hover:scale-110"
                        >
                          <Download className="w-6 h-6" />
                        </a>
                      </div>
                    </div>

                    <div className="p-5 bg-slate-900/90 flex-1 flex flex-col justify-between">
                      <div>
                        <h4 className="font-bold text-base text-slate-200 mb-1 line-clamp-1" title={title ?? `Short #${i + 1}`}>
                          {title ?? `Generated Short #${i + 1}`}
                        </h4>
                        <p className="text-xs text-slate-500 font-mono">Optimized for {dest}</p>
                      </div>

                      {/* Card Actions: Download + 1-Click Post to YouTube */}
                      <div className="mt-5 pt-4 border-t border-slate-800/80 flex items-center justify-between gap-2">
                        <a
                          href={`${BACKEND_URL}/${path}`}
                          download
                          className="text-xs text-slate-400 hover:text-slate-200 font-semibold flex items-center gap-1.5"
                        >
                          <Download className="w-3.5 h-3.5" /> Save
                        </a>

                        <button
                          onClick={() => handleOpenPublishModal(clip)}
                          className="px-3.5 py-1.5 bg-red-600 hover:bg-red-500 text-white rounded-xl text-xs font-bold flex items-center gap-1.5 shadow-[0_0_15px_rgba(239,68,68,0.35)] hover:scale-105 transition-all cursor-pointer"
                        >
                          <Video className="w-3.5 h-3.5" /> Post to YouTube
                        </button>
                      </div>
                    </div>
                  </motion.div>
                );
              })}
            </div>
          </motion.div>
        )}

      </div>

      {/* ── MODAL: YOUTUBE OAUTH CREDENTIALS SETUP ── */}
      <AnimatePresence>
        {showYoutubeConfigModal && (
          <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4">
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="bg-slate-900 border border-slate-800 rounded-3xl p-6 sm:p-8 max-w-lg w-full shadow-[0_0_60px_rgba(0,0,0,0.8)] relative"
            >
              <div className="flex items-center justify-between mb-5">
                <h3 className="text-xl font-bold text-white flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg bg-red-500/20 border border-red-500/40 flex items-center justify-center text-red-500">
                    <Video className="w-4 h-4" />
                  </div>
                  Link YouTube Channel
                </h3>
                <button
                  onClick={() => setShowYoutubeConfigModal(false)}
                  className="text-slate-500 hover:text-white transition-colors cursor-pointer"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              <div className="space-y-4 text-xs">
                <div className="p-4 bg-slate-950 rounded-2xl border border-slate-800/90 space-y-2.5 text-slate-300 leading-relaxed">
                  <div className="flex items-center justify-between">
                    <p className="font-bold text-indigo-300">Google Cloud Setup (Project 242796880153):</p>
                    <a
                      href="https://console.cloud.google.com/apis/credentials?project=242796880153"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-indigo-400 hover:text-indigo-300 font-bold inline-flex items-center gap-1"
                    >
                      Open Cloud Console <ExternalLink className="w-3 h-3" />
                    </a>
                  </div>
                  <ol className="list-decimal list-inside space-y-1 text-slate-400">
                    <li>
                      <a href="https://console.cloud.google.com/apis/library/youtube.googleapis.com?project=242796880153" target="_blank" rel="noopener noreferrer" className="text-indigo-400 underline font-medium">
                        Enable YouTube Data API v3
                      </a> in your Google Cloud project.
                    </li>
                    <li>Go to <b>Credentials &gt; Create Credentials &gt; OAuth client ID</b>.</li>
                    <li>Select Application type: <b>Web application</b>.</li>
                    <li>
                      Add Authorized redirect URI:{' '}
                      <code className="bg-slate-900 px-1.5 py-0.5 rounded text-pink-300 font-mono text-[11px]">
                        {youtubeStatus.redirect_uri || 'http://localhost:8000/api/youtube/callback'}
                      </code>
                    </li>
                    <li>Paste your generated Client ID and Client Secret below:</li>
                  </ol>

                  <div className="p-2.5 bg-amber-500/10 border border-amber-500/20 rounded-xl text-amber-300/90 text-[11px] leading-normal flex items-start gap-2">
                    <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5 text-amber-400" />
                    <span><b>Fix for Error 401 invalid_client:</b> This error occurs when Google cannot find the Client ID in its database. Make sure your OAuth Client ID is created in Google Cloud Console under project 242796880153 and ends with <code>.apps.googleusercontent.com</code>.</span>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-bold text-slate-300 mb-1.5">OAuth Client ID</label>
                  <input
                    type="text"
                    placeholder="242796880153-xxxxxxxx.apps.googleusercontent.com"
                    value={youtubeConfigForm.clientId}
                    onChange={(e) => setYoutubeConfigForm(f => ({ ...f, clientId: e.target.value }))}
                    className="w-full bg-slate-950 border border-slate-700/80 rounded-xl px-3.5 py-2.5 text-xs text-white focus:outline-none focus:border-red-500 font-mono"
                  />
                </div>

                <div>
                  <label className="block text-xs font-bold text-slate-300 mb-1.5">OAuth Client Secret</label>
                  <input
                    type="password"
                    placeholder="GOCSPX-xxxxxxxxxxxxxxxx"
                    value={youtubeConfigForm.clientSecret}
                    onChange={(e) => setYoutubeConfigForm(f => ({ ...f, clientSecret: e.target.value }))}
                    className="w-full bg-slate-950 border border-slate-700/80 rounded-xl px-3.5 py-2.5 text-xs text-white focus:outline-none focus:border-red-500 font-mono"
                  />
                </div>

                <div className="pt-2 flex gap-3">
                  <button
                    onClick={() => setShowYoutubeConfigModal(false)}
                    className="flex-1 py-3 bg-slate-800 hover:bg-slate-700 text-slate-300 font-bold rounded-xl text-xs transition-all cursor-pointer"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleSaveYoutubeConfig}
                    disabled={!youtubeConfigForm.clientId || !youtubeConfigForm.clientSecret}
                    className="flex-1 py-3 bg-red-600 hover:bg-red-500 disabled:opacity-40 text-white font-bold rounded-xl text-xs transition-all shadow-[0_0_20px_rgba(239,68,68,0.3)] cursor-pointer"
                  >
                    Save & Authorize
                  </button>
                </div>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* ── MODAL: 1-CLICK POST TO YOUTUBE SHORTS ── */}
      <AnimatePresence>
        {publishingClip && (
          <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4">
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="bg-slate-900 border border-red-500/30 rounded-3xl p-6 sm:p-8 max-w-xl w-full shadow-[0_0_60px_rgba(239,68,68,0.15)] relative max-h-[90vh] overflow-y-auto"
            >
              {/* Header */}
              <div className="flex items-center justify-between mb-5">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-red-500/20 border border-red-500/40 flex items-center justify-center text-red-500">
                    <Video className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 className="text-xl font-bold text-white">Post to YouTube Shorts</h3>
                    <p className="text-xs text-slate-400">Publish high-reach title & viral description directly</p>
                  </div>
                </div>
                <button
                  onClick={() => setPublishingClip(null)}
                  className="text-slate-500 hover:text-white transition-colors cursor-pointer"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              {/* Connected Channel Display */}
              {youtubeStatus.connected && youtubeStatus.channel ? (
                <div className="flex items-center gap-3 p-3 bg-slate-950/80 border border-slate-800 rounded-2xl mb-5">
                  {youtubeStatus.channel.avatar ? (
                    <img src={youtubeStatus.channel.avatar} className="w-9 h-9 rounded-full border border-red-400 object-cover" />
                  ) : (
                    <Video className="w-6 h-6 text-red-500" />
                  )}
                  <div className="flex-1 min-w-0">
                    <span className="text-[10px] text-slate-400 uppercase font-bold tracking-wider">Publishing to Channel:</span>
                    <p className="text-sm font-bold text-white truncate">{youtubeStatus.channel.title}</p>
                  </div>
                  <span className="text-[10px] uppercase font-bold text-emerald-400 bg-emerald-500/10 px-2.5 py-1 rounded-full border border-emerald-500/30">
                    Connected
                  </span>
                </div>
              ) : (
                <div className="p-4 bg-amber-500/10 border border-amber-500/30 rounded-2xl mb-5 text-xs text-amber-300 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <AlertCircle className="w-4 h-4 text-amber-400 shrink-0" />
                    <span>Connect your YouTube channel before posting.</span>
                  </div>
                  <button
                    onClick={() => { setPublishingClip(null); handleConnectYoutube(); }}
                    className="px-3 py-1.5 bg-red-600 hover:bg-red-500 text-white rounded-lg font-bold text-xs cursor-pointer shrink-0"
                  >
                    Connect
                  </button>
                </div>
              )}

              {/* SUCCESS STATE */}
              {publishResult ? (
                <div className="text-center py-6 space-y-4">
                  <div className="w-14 h-14 rounded-full bg-emerald-500/20 border border-emerald-500/40 text-emerald-400 flex items-center justify-center mx-auto shadow-[0_0_30px_rgba(16,185,129,0.3)]">
                    <CheckCircle className="w-8 h-8" />
                  </div>
                  <h4 className="text-2xl font-black text-white">Short Published Successfully!</h4>
                  <p className="text-xs text-slate-300 max-w-sm mx-auto">
                    Your video is live on YouTube. Click below to view the Short in your browser.
                  </p>

                  <div className="pt-2 flex flex-col sm:flex-row gap-3 justify-center">
                    <a
                      href={publishResult.youtube_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="px-6 py-3 bg-red-600 hover:bg-red-500 text-white font-bold text-xs rounded-xl flex items-center justify-center gap-2 shadow-[0_0_20px_rgba(239,68,68,0.4)]"
                    >
                      <ExternalLink className="w-4 h-4" /> Open on YouTube Shorts
                    </a>
                    <button
                      onClick={() => setPublishingClip(null)}
                      className="px-6 py-3 bg-slate-800 hover:bg-slate-700 text-slate-300 font-bold text-xs rounded-xl"
                    >
                      Done
                    </button>
                  </div>
                </div>
              ) : (
                /* FORM INPUTS */
                <div className="space-y-4 text-xs">
                  {/* Title */}
                  <div>
                    <div className="flex justify-between items-center mb-1">
                      <label className="font-bold text-slate-300">Video Title (Auto-appends #Shorts):</label>
                      <span className={`font-mono text-[11px] ${publishForm.title.length > 95 ? 'text-amber-400' : 'text-slate-500'}`}>
                        {publishForm.title.length}/100
                      </span>
                    </div>
                    <input
                      type="text"
                      maxLength={100}
                      value={publishForm.title}
                      onChange={(e) => setPublishForm(f => ({ ...f, title: e.target.value }))}
                      className="w-full bg-slate-950 border border-slate-700/80 rounded-xl px-3.5 py-2.5 text-xs text-white focus:outline-none focus:border-red-500 font-medium"
                    />
                  </div>

                  {/* Description */}
                  <div>
                    <label className="block font-bold text-slate-300 mb-1">Description (AI Caption & Call-to-Action):</label>
                    <textarea
                      rows={4}
                      value={publishForm.description}
                      onChange={(e) => setPublishForm(f => ({ ...f, description: e.target.value }))}
                      className="w-full bg-slate-950 border border-slate-700/80 rounded-xl p-3 text-xs text-slate-200 focus:outline-none focus:border-red-500 font-normal leading-relaxed"
                    />
                  </div>

                  {/* Tags */}
                  <div>
                    <label className="block font-bold text-slate-300 mb-1">Tags (Comma-separated):</label>
                    <input
                      type="text"
                      value={publishForm.tags}
                      onChange={(e) => setPublishForm(f => ({ ...f, tags: e.target.value }))}
                      className="w-full bg-slate-950 border border-slate-700/80 rounded-xl px-3.5 py-2 text-xs text-slate-200 focus:outline-none focus:border-red-500 font-mono"
                    />
                  </div>

                  {/* Privacy Status */}
                  <div>
                    <label className="block font-bold text-slate-300 mb-1">Privacy Status:</label>
                    <div className="grid grid-cols-3 gap-2.5">
                      {['public', 'unlisted', 'private'].map(p => (
                        <button
                          key={p}
                          type="button"
                          onClick={() => setPublishForm(f => ({ ...f, privacyStatus: p }))}
                          className={`py-2 px-3 rounded-xl border text-center capitalize font-semibold transition-all cursor-pointer ${
                            publishForm.privacyStatus === p
                              ? 'bg-red-500/20 border-red-500 text-white'
                              : 'bg-slate-950 border-slate-800 text-slate-400 hover:bg-slate-800'
                          }`}
                        >
                          {p}
                        </button>
                      ))}
                    </div>
                  </div>

                  {publishError && (
                    <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-xl text-red-400 text-xs">
                      {publishError}
                    </div>
                  )}

                  {/* Submit Button */}
                  <div className="pt-2">
                    <button
                      onClick={handlePublishToYoutube}
                      disabled={isPublishing || !youtubeStatus.connected}
                      className="w-full py-3.5 bg-gradient-to-r from-red-600 to-pink-600 hover:shadow-[0_0_30px_rgba(239,68,68,0.4)] disabled:opacity-50 text-white font-bold rounded-xl text-sm flex items-center justify-center gap-2 transition-all cursor-pointer"
                    >
                      {isPublishing ? (
                        <>
                          <RefreshCw className="w-4 h-4 animate-spin" />
                          Uploading to YouTube...
                        </>
                      ) : (
                        <>
                          <Send className="w-4 h-4" />
                          Post Short Now
                        </>
                      )}
                    </button>
                  </div>
                </div>
              )}
            </motion.div>
          </div>
        )}
      </AnimatePresence>

    </div>
  );
}

export default App;
