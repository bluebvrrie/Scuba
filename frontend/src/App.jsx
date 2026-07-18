import React, { useState, useEffect } from 'react';
import { 
  BookOpen, 
  Award, 
  Calendar, 
  Upload, 
  Sparkles, 
  User, 
  Search, 
  CheckCircle, 
  XCircle, 
  Clock, 
  Flame, 
  FileText, 
  ArrowRight, 
  HelpCircle, 
  RefreshCw,
  Info,
  ChevronRight,
  TrendingUp
} from 'lucide-react';

const API_BASE = "http://localhost:8000";

export default function App() {
  const [student, setStudent] = useState(null);
  const [studentId, setStudentId] = useState(localStorage.getItem('scuba_student_id') || '');
  const [currentTab, setCurrentTab] = useState('dashboard');
  
  // Registration form states
  const [regName, setRegName] = useState('');
  const [regEmail, setRegEmail] = useState('');
  const [regGrade, setRegGrade] = useState('College');
  const [regTopics, setRegTopics] = useState('physics, chemistry, algebra, history');
  
  // Dashboard & Analytics states
  const [dashboardData, setDashboardData] = useState(null);
  const [dashboardLoading, setDashboardLoading] = useState(false);
  const [backendError, setBackendError] = useState(false);
  
  // Study Tab states
  const [studyTopic, setStudyTopic] = useState('');
  const [studyDifficulty, setStudyDifficulty] = useState('intermediate');
  const [studyResult, setStudyResult] = useState(null);
  const [studyLoading, setStudyLoading] = useState(false);
  const [studySubTab, setStudySubTab] = useState('simple'); // simple, steps, analogy
  const [activeCardIndex, setActiveCardIndex] = useState(0);
  const [cardFlipped, setCardFlipped] = useState(false);
  
  // Quiz Tab states
  const [quizSetup, setQuizSetup] = useState({ count: 5, topic: '', adaptive: true });
  const [activeQuiz, setActiveQuiz] = useState(null); // Full quiz from backend
  const [quizAnswers, setQuizAnswers] = useState({}); // qId -> answer
  const [quizLoading, setQuizLoading] = useState(false);
  const [quizSubmitted, setQuizSubmitted] = useState(false);
  const [quizResult, setQuizResult] = useState(null); // Grading result from backend
  const [quizStartTime, setQuizStartTime] = useState(null);
  const [quizTimer, setQuizTimer] = useState(0);

  // Upload Tab states
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadTopic, setUploadTopic] = useState('');
  const [uploadLoading, setUploadLoading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState(null);

  // Load student profile & dashboard on start/change
  useEffect(() => {
    if (studentId) {
      fetchStudentProfile();
      fetchDashboard();
    }
  }, [studentId]);

  // Quiz timer effect
  useEffect(() => {
    let interval = null;
    if (activeQuiz && !quizSubmitted) {
      interval = setInterval(() => {
        setQuizTimer(prev => prev + 1);
      }, 1000);
    } else {
      clearInterval(interval);
    }
    return () => clearInterval(interval);
  }, [activeQuiz, quizSubmitted]);

  const fetchStudentProfile = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/students/${studentId}`);
      if (res.ok) {
        const data = await res.json();
        setStudent(data);
        setBackendError(false);
      } else {
        // Clear local storage if student not found
        setStudentId('');
        localStorage.removeItem('scuba_student_id');
      }
    } catch (err) {
      console.error(err);
      setBackendError(true);
    }
  };

  const fetchDashboard = async () => {
    if (!studentId) return;
    setDashboardLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/students/${studentId}/dashboard`);
      if (res.ok) {
        const data = await res.json();
        setDashboardData(data);
        setBackendError(false);
      } else {
        setBackendError(true);
      }
    } catch (err) {
      console.error(err);
      setBackendError(true);
    } finally {
      setDashboardLoading(false);
    }
  };

  const handleRegister = async (e) => {
    e.preventDefault();
    if (!regName.trim()) return;
    
    const topicsArray = regTopics.split(',').map(t => t.trim().toLowerCase()).filter(t => t);
    
    try {
      const res = await fetch(`${API_BASE}/api/students`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: regName,
          email: regEmail || null,
          grade_level: regGrade,
          curriculum_topics: topicsArray
        })
      });
      if (res.ok) {
        const data = await res.json();
        setStudentId(data.student_id);
        localStorage.setItem('scuba_student_id', data.student_id);
        setBackendError(false);
      } else {
        alert("Registration failed. Please check the backend service.");
      }
    } catch (err) {
      console.error(err);
      alert("Could not connect to the backend server. Is it running on port 8000?");
    }
  };

  const handleLogout = () => {
    setStudent(null);
    setStudentId('');
    setDashboardData(null);
    localStorage.removeItem('scuba_student_id');
  };

  const handleIngestDocument = async (e) => {
    e.preventDefault();
    if (!uploadFile) return;
    setUploadLoading(true);
    setUploadMessage(null);
    
    const formData = new FormData();
    formData.append('file', uploadFile);
    if (uploadTopic) {
      formData.append('topic', uploadTopic.trim().toLowerCase());
    }
    
    try {
      const res = await fetch(`${API_BASE}/api/students/${studentId}/upload`, {
        method: 'POST',
        body: formData
      });
      if (res.ok) {
        const data = await res.json();
        setUploadMessage({ type: 'success', text: `Document '${data.filename}' successfully ingested and parsed! ${data.chunks_indexed} chunks indexed.` });
        setUploadFile(null);
        setUploadTopic('');
        fetchDashboard();
      } else {
        const err = await res.json();
        setUploadMessage({ type: 'error', text: `Upload failed: ${err.detail || 'Unknown error'}` });
      }
    } catch (err) {
      console.error(err);
      setUploadMessage({ type: 'error', text: "Server connection failed." });
    } finally {
      setUploadLoading(false);
    }
  };

  const handleGenerateLesson = async (e) => {
    e.preventDefault();
    if (!studyTopic.trim()) return;
    setStudyLoading(true);
    setStudyResult(null);
    setActiveCardIndex(0);
    setCardFlipped(false);
    
    try {
      const res = await fetch(`${API_BASE}/api/students/${studentId}/learn`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          topic: studyTopic.trim(),
          difficulty: studyDifficulty
        })
      });
      if (res.ok) {
        const data = await res.json();
        setStudyResult(data);
        setStudySubTab('simple');
      } else {
        alert("Lesson generation failed.");
      }
    } catch (err) {
      console.error(err);
      alert("Failed to connect to the backend api.");
    } finally {
      setStudyLoading(false);
    }
  };

  const handleStartQuiz = async () => {
    setQuizLoading(true);
    setActiveQuiz(null);
    setQuizSubmitted(false);
    setQuizResult(null);
    setQuizAnswers({});
    setQuizTimer(0);
    
    try {
      const res = await fetch(`${API_BASE}/api/students/${studentId}/quiz/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          num_questions: quizSetup.count,
          topics: quizSetup.topic ? [quizSetup.topic.trim().toLowerCase()] : null,
          adaptive: quizSetup.adaptive
        })
      });
      if (res.ok) {
        const data = await res.json();
        setActiveQuiz(data);
        setQuizStartTime(new Date());
      } else {
        alert("Failed to generate quiz. Try adding more documents or topics.");
      }
    } catch (err) {
      console.error(err);
      alert("Failed to communicate with API.");
    } finally {
      setQuizLoading(false);
    }
  };

  const handleSelectOption = (qId, option) => {
    setQuizAnswers(prev => ({ ...prev, [qId]: option }));
  };

  const handleSubmitQuiz = async () => {
    // Check that all questions have answers
    const unansweredCount = activeQuiz.questions.filter(q => !quizAnswers[q.id]).length;
    if (unansweredCount > 0) {
      if (!confirm(`You have ${unansweredCount} unanswered questions. Submit anyway?`)) {
        return;
      }
    }
    
    setQuizLoading(true);
    const answersList = Object.entries(quizAnswers).map(([qId, ans]) => ({
      question_id: qId,
      answer: ans,
      time_taken_seconds: Math.round(quizTimer / activeQuiz.questions.length)
    }));
    
    try {
      const res = await fetch(`${API_BASE}/api/students/${studentId}/quiz/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          quiz_data: activeQuiz,
          answers: answersList,
          learning_goals: student.curriculum_topics,
          minutes_per_day: 60
        })
      });
      if (res.ok) {
        const data = await res.json();
        setQuizResult(data);
        setQuizSubmitted(true);
        fetchDashboard(); // refresh stats
      } else {
        alert("Evaluation failed.");
      }
    } catch (err) {
      console.error(err);
      alert("Network error submiting quiz.");
    } finally {
      setQuizLoading(false);
    }
  };

  // Helper to trigger recommended study topic
  const quickStudyTopic = (topicName) => {
    setStudyTopic(topicName);
    setCurrentTab('study');
    setStudyResult(null);
  };

  // Welcome Registration View
  if (!studentId || !student) {
    return (
      <div className="min-h-screen bg-dark-950 flex flex-col items-center justify-center p-4 relative overflow-hidden">
        {/* Glow circles behind */}
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-primary-600 rounded-full filter blur-[150px] opacity-20 animate-pulse-slow"></div>
        <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-accent-cyan rounded-full filter blur-[150px] opacity-15 animate-pulse-slow"></div>
        
        <div className="max-w-md w-full glass-panel rounded-2xl p-8 shadow-2xl border border-white/10 relative z-10">
          <div className="flex items-center gap-3 mb-6 justify-center">
            <div className="p-3 bg-gradient-to-tr from-primary-600 to-accent-cyan rounded-xl shadow-lg animate-float">
              <BookOpen className="w-8 h-8 text-white" />
            </div>
            <div>
              <h1 className="text-3xl font-extrabold tracking-tight text-white">SCUBA</h1>
              <p className="text-xs text-accent-cyan tracking-wider font-semibold uppercase">Multi-Agent AI Learning</p>
            </div>
          </div>
          
          <h2 className="text-xl font-bold text-slate-100 text-center mb-6">Initialize Learning Profile</h2>
          
          {backendError && (
            <div className="mb-6 p-4 rounded-xl bg-red-950/40 border border-red-500/30 text-red-300 text-sm flex gap-3 items-start">
              <Info className="w-5 h-5 flex-shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold block">Connection Refused</span>
                FastAPI backend is offline. Run <code className="bg-red-950 px-1 py-0.5 rounded text-xs text-red-200">python backend/api.py</code> on your computer to connect.
              </div>
            </div>
          )}

          <form onSubmit={handleRegister} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Student Name</label>
              <input 
                type="text" 
                required 
                value={regName}
                onChange={e => setRegName(e.target.value)}
                placeholder="e.g. Alice Vance" 
                className="w-full bg-dark-900 border border-white/10 rounded-xl px-4 py-3 text-white placeholder-slate-500 focus:outline-none focus:border-primary-500 transition"
              />
            </div>
            
            <div>
              <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Email Address (Optional)</label>
              <input 
                type="email" 
                value={regEmail}
                onChange={e => setRegEmail(e.target.value)}
                placeholder="alice@school.edu" 
                className="w-full bg-dark-900 border border-white/10 rounded-xl px-4 py-3 text-white placeholder-slate-500 focus:outline-none focus:border-primary-500 transition"
              />
            </div>
            
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Grade Level</label>
                <select 
                  value={regGrade}
                  onChange={e => setRegGrade(e.target.value)}
                  className="w-full bg-dark-900 border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-primary-500 transition"
                >
                  <option value="Middle School">Middle School</option>
                  <option value="High School">High School</option>
                  <option value="College">College</option>
                  <option value="Professional">Professional</option>
                </select>
              </div>
              
              <div>
                <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Quick Start Demo ID</label>
                <button 
                  type="button"
                  onClick={() => {
                    setStudentId("demo_student");
                    localStorage.setItem('scuba_student_id', "demo_student");
                  }}
                  className="w-full bg-dark-700/60 border border-white/10 hover:border-primary-500/40 text-slate-300 font-semibold rounded-xl py-3 text-sm transition text-center"
                >
                  Load Demo Profile
                </button>
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Curriculum Topics (comma separated)</label>
              <input 
                type="text" 
                value={regTopics}
                onChange={e => setRegTopics(e.target.value)}
                className="w-full bg-dark-900 border border-white/10 rounded-xl px-4 py-3 text-white placeholder-slate-500 focus:outline-none focus:border-primary-500 transition"
              />
            </div>
            
            <button 
              type="submit" 
              className="w-full glow-btn bg-gradient-to-r from-primary-600 to-primary-700 hover:from-primary-500 hover:to-primary-600 text-white font-bold rounded-xl py-3 shadow-lg shadow-primary-500/25 transition mt-6 flex items-center justify-center gap-2"
            >
              <User className="w-5 h-5" />
              Create Profile & Connect
            </button>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-dark-950 flex flex-col md:flex-row relative">
      {/* Sidebar Navigation */}
      <div className="w-full md:w-64 bg-dark-900 border-r border-white/5 flex flex-col justify-between flex-shrink-0 relative z-20">
        <div>
          {/* Logo Brand */}
          <div className="p-6 border-b border-white/5 flex items-center gap-3">
            <div className="p-2 bg-gradient-to-tr from-primary-600 to-accent-cyan rounded-lg shadow-md">
              <BookOpen className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-extrabold tracking-tight text-white">SCUBA</h1>
              <p className="text-[10px] text-accent-cyan tracking-wider font-semibold uppercase">Multi-Agent AI</p>
            </div>
          </div>
          
          {/* User profile brief */}
          <div className="px-6 py-4 flex items-center gap-3 border-b border-white/5 bg-dark-950/20">
            <div className="w-9 h-9 bg-primary-600/20 border border-primary-500/30 rounded-full flex items-center justify-center">
              <User className="w-5 h-5 text-primary-400" />
            </div>
            <div className="overflow-hidden">
              <p className="text-sm font-semibold text-slate-200 truncate">{student?.name || 'Loading...'}</p>
              <span className="text-[10px] text-slate-400 block tracking-wider uppercase font-semibold">{student?.grade_level}</span>
            </div>
          </div>
          
          {/* Navigation Links */}
          <nav className="p-4 space-y-1">
            {[
              { id: 'dashboard', label: 'Dashboard', icon: Award },
              { id: 'study', label: 'Study Terminal', icon: Search },
              { id: 'quiz', label: 'Quiz Arena', icon: Flame },
              { id: 'upload', label: 'Resource Upload', icon: Upload },
            ].map(item => {
              const Icon = item.icon;
              const isActive = currentTab === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => setCurrentTab(item.id)}
                  className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition duration-200 ${
                    isActive 
                      ? 'bg-primary-500/10 text-primary-400 border border-primary-500/20 shadow-inner' 
                      : 'text-slate-400 hover:bg-white/5 hover:text-slate-200 border border-transparent'
                  }`}
                >
                  <Icon className="w-5 h-5" />
                  {item.label}
                </button>
              );
            })}
          </nav>
        </div>
        
        {/* Footer actions */}
        <div className="p-4 border-t border-white/5 space-y-2">
          {backendError && (
            <div className="p-3 bg-red-950/30 border border-red-500/20 rounded-xl text-[10px] text-red-300 flex items-start gap-2">
              <Info className="w-4 h-4 flex-shrink-0" />
              <span>Backend Offline. Check port 8000</span>
            </div>
          )}
          <button 
            onClick={handleLogout}
            className="w-full bg-dark-800 hover:bg-dark-700 text-slate-400 hover:text-slate-200 text-xs font-semibold py-2.5 px-4 rounded-xl border border-white/5 transition"
          >
            Switch Profile
          </button>
        </div>
      </div>

      {/* Main Content Area */}
      <main className="flex-grow p-6 md:p-8 overflow-y-auto max-h-screen relative z-10">
        {/* Glow lights */}
        <div className="absolute top-0 right-1/4 w-80 h-80 bg-primary-600 rounded-full filter blur-[150px] opacity-10 pointer-events-none"></div>

        {/* Dashboard Tab */}
        {currentTab === 'dashboard' && (
          <div className="space-y-6 animate-fadeIn">
            {/* Header info */}
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
              <div>
                <h2 className="text-3xl font-extrabold text-white tracking-tight">Analytics Dashboard</h2>
                <p className="text-slate-400 text-sm">Longitudinal insights compiled by the Evaluation & Planning Agent.</p>
              </div>
              <button 
                onClick={fetchDashboard}
                disabled={dashboardLoading}
                className="p-2.5 bg-dark-900 border border-white/10 rounded-xl hover:bg-dark-800 text-slate-300 transition flex items-center gap-2 text-sm disabled:opacity-50"
              >
                <RefreshCw className={`w-4 h-4 ${dashboardLoading ? 'animate-spin' : ''}`} />
                Refresh Data
              </button>
            </div>

            {/* Quick stats grid */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="glass-panel rounded-2xl p-5 border border-white/5 flex items-center justify-between shadow-lg">
                <div>
                  <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">Streak</span>
                  <div className="text-3xl font-extrabold text-white flex items-center gap-1.5 mt-1">
                    {dashboardData?.learning_streak || 0}
                    <span className="text-xs text-orange-400 font-medium">days</span>
                  </div>
                </div>
                <div className="p-3 bg-orange-500/10 border border-orange-500/20 text-orange-400 rounded-xl animate-float">
                  <Flame className="w-6 h-6" />
                </div>
              </div>

              <div className="glass-panel rounded-2xl p-5 border border-white/5 flex items-center justify-between shadow-lg">
                <div>
                  <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">Avg Score</span>
                  <div className="text-3xl font-extrabold text-white mt-1">
                    {dashboardData?.average_score ? `${dashboardData.average_score}%` : 'N/A'}
                  </div>
                </div>
                <div className="p-3 bg-green-500/10 border border-green-500/20 text-green-400 rounded-xl">
                  <Award className="w-6 h-6" />
                </div>
              </div>

              <div className="glass-panel rounded-2xl p-5 border border-white/5 flex items-center justify-between shadow-lg">
                <div>
                  <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">Study Time</span>
                  <div className="text-3xl font-extrabold text-white flex items-center gap-1.5 mt-1">
                    {dashboardData?.learning_time ? Math.round(dashboardData.learning_time) : 0}
                    <span className="text-xs text-primary-400 font-medium">min</span>
                  </div>
                </div>
                <div className="p-3 bg-primary-500/10 border border-primary-500/20 text-primary-400 rounded-xl">
                  <Clock className="w-6 h-6" />
                </div>
              </div>

              <div className="glass-panel rounded-2xl p-5 border border-white/5 flex items-center justify-between shadow-lg">
                <div>
                  <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">Documents</span>
                  <div className="text-3xl font-extrabold text-white mt-1">
                    {dashboardData?.analytics_report?.performance_analytics?.total_documents_uploaded || 0}
                  </div>
                </div>
                <div className="p-3 bg-accent-cyan/10 border border-accent-cyan/20 text-accent-cyan rounded-xl">
                  <FileText className="w-6 h-6" />
                </div>
              </div>
            </div>

            {/* Core Panels Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              
              {/* Progress & Mastery */}
              <div className="glass-panel rounded-2xl p-6 border border-white/5 shadow-lg lg:col-span-2 space-y-6">
                <div>
                  <h3 className="text-lg font-bold text-white flex items-center gap-2">
                    <TrendingUp className="w-5 h-5 text-primary-400" />
                    Topic Mastery Levels
                  </h3>
                  <p className="text-xs text-slate-400">Mastery percentages calculated from recent quiz attempts.</p>
                </div>
                
                {dashboardData?.progress && Object.keys(dashboardData.progress).length > 0 ? (
                  <div className="space-y-4">
                    {Object.entries(dashboardData.progress).map(([topic, mastery]) => {
                      // Determine color coding
                      let barColor = 'bg-primary-500';
                      let textColor = 'text-primary-400';
                      if (mastery >= 80) {
                        barColor = 'bg-green-500';
                        textColor = 'text-green-400';
                      } else if (mastery < 60) {
                        barColor = 'bg-red-500';
                        textColor = 'text-red-400';
                      }
                      
                      return (
                        <div key={topic} className="space-y-1.5">
                          <div className="flex justify-between text-sm">
                            <span className="font-semibold text-slate-200 capitalize">{topic}</span>
                            <span className={`font-bold ${textColor}`}>{mastery.toFixed(0)}% Mastery</span>
                          </div>
                          <div className="w-full bg-dark-900 rounded-full h-2.5 border border-white/5 overflow-hidden">
                            <div className={`h-full ${barColor} rounded-full`} style={{ width: `${mastery}%` }}></div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="py-10 text-center border border-dashed border-white/5 rounded-xl text-slate-400 text-sm">
                    No learning analytics data available yet. Open the <button onClick={() => setCurrentTab('study')} className="text-primary-400 underline hover:text-primary-300">Study Terminal</button> or take a <button onClick={() => setCurrentTab('quiz')} className="text-primary-400 underline hover:text-primary-300">Quiz</button> to see your stats populate!
                  </div>
                )}

                {/* Topics status groups */}
                {dashboardData && (
                  <div className="grid grid-cols-2 gap-4 pt-4 border-t border-white/5">
                    <div>
                      <span className="text-xs font-bold text-green-400 flex items-center gap-1.5 mb-2">
                        <span className="w-2 h-2 rounded-full bg-green-400"></span>
                        Strong Topics ({dashboardData.strong_topics?.length || 0})
                      </span>
                      <div className="flex flex-wrap gap-1.5">
                        {dashboardData.strong_topics?.map(t => (
                          <span key={t} className="text-xs bg-green-500/10 border border-green-500/20 text-green-300 px-2 py-0.5 rounded-lg capitalize">{t}</span>
                        )) || <span className="text-xs text-slate-500">None yet</span>}
                      </div>
                    </div>
                    <div>
                      <span className="text-xs font-bold text-red-400 flex items-center gap-1.5 mb-2">
                        <span className="w-2 h-2 rounded-full bg-red-400"></span>
                        Weak Topics ({dashboardData.weak_topics?.length || 0})
                      </span>
                      <div className="flex flex-wrap gap-1.5">
                        {dashboardData.weak_topics?.map(t => (
                          <span key={t} className="text-xs bg-red-500/10 border border-red-500/20 text-red-300 px-2 py-0.5 rounded-lg capitalize">{t}</span>
                        )) || <span className="text-xs text-slate-500">None yet</span>}
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* Recommended & Study Plan sidebar */}
              <div className="space-y-6">
                <div className="glass-panel rounded-2xl p-6 border border-white/5 shadow-lg space-y-4">
                  <h3 className="text-md font-bold text-white flex items-center gap-2">
                    <Sparkles className="w-5 h-5 text-accent-cyan" />
                    Recommended Next
                  </h3>
                  <p className="text-xs text-slate-400">Personalized revision topics compiled based on weak scores and curriculum gaps.</p>
                  
                  {dashboardData?.recommended_topics && dashboardData.recommended_topics.length > 0 ? (
                    <div className="space-y-2">
                      {dashboardData.recommended_topics.map(topic => (
                        <button
                          key={topic}
                          onClick={() => quickStudyTopic(topic)}
                          className="w-full flex items-center justify-between p-3 bg-dark-900 border border-white/5 rounded-xl hover:border-primary-500/30 text-left text-sm text-slate-200 hover:text-white transition group"
                        >
                          <span className="capitalize font-semibold">{topic}</span>
                          <span className="p-1 rounded-lg bg-primary-500/10 border border-primary-500/20 group-hover:bg-primary-500/25 transition">
                            <ArrowRight className="w-4 h-4 text-primary-400" />
                          </span>
                        </button>
                      ))}
                    </div>
                  ) : (
                    <div className="p-4 bg-dark-900/50 border border-dashed border-white/5 text-center text-slate-400 text-xs rounded-xl">
                      Add curriculum topics or complete quizzes to get recommendations.
                    </div>
                  )}
                </div>

                <div className="glass-panel rounded-2xl p-6 border border-white/5 shadow-lg space-y-3">
                  <h3 className="text-md font-bold text-slate-200 flex items-center gap-2">
                    <Calendar className="w-5 h-5 text-primary-400" />
                    Study Details
                  </h3>
                  <div className="space-y-2 text-xs text-slate-400">
                    <div className="flex justify-between border-b border-white/5 pb-2">
                      <span>Curriculum Topics:</span>
                      <span className="font-semibold text-slate-200 capitalize">{student?.curriculum_topics?.join(', ') || 'General'}</span>
                    </div>
                    <div className="flex justify-between border-b border-white/5 pb-2">
                      <span>Total Quizzes Taken:</span>
                      <span className="font-semibold text-slate-200">{dashboardData?.analytics_report?.performance_analytics?.total_quizzes_taken || 0}</span>
                    </div>
                    <div className="flex justify-between">
                      <span>Profile Created:</span>
                      <span className="font-semibold text-slate-200">{student?.created_at ? new Date(student.created_at).toLocaleDateString() : 'N/A'}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Study Terminal Tab */}
        {currentTab === 'study' && (
          <div className="space-y-6 animate-fadeIn">
            <div>
              <h2 className="text-3xl font-extrabold text-white tracking-tight">Study Terminal</h2>
              <p className="text-slate-400 text-sm">RAG Research Agent retrieves data; Teaching Agent crafts custom, interactive lessons.</p>
            </div>

            {/* Input Form */}
            <form onSubmit={handleGenerateLesson} className="glass-panel rounded-2xl p-6 border border-white/5 shadow-lg space-y-4">
              <div className="flex flex-col md:flex-row gap-4">
                <div className="flex-grow relative">
                  <Search className="w-5 h-5 text-slate-400 absolute left-4 top-1/2 -translate-y-1/2" />
                  <input 
                    type="text"
                    required
                    value={studyTopic}
                    onChange={e => setStudyTopic(e.target.value)}
                    placeholder="Enter concept name (e.g. Barkhausen criterion, Ohm's Law, covalent bonds)..."
                    className="w-full bg-dark-900 border border-white/10 rounded-xl pl-12 pr-4 py-3 text-white placeholder-slate-500 focus:outline-none focus:border-primary-500 transition"
                  />
                </div>
                
                <div className="flex gap-4">
                  <select 
                    value={studyDifficulty}
                    onChange={e => setStudyDifficulty(e.target.value)}
                    className="bg-dark-900 border border-white/10 rounded-xl px-4 py-3 text-slate-300 focus:outline-none focus:border-primary-500 transition"
                  >
                    <option value="beginner">Beginner Level</option>
                    <option value="intermediate">Intermediate Level</option>
                    <option value="advanced">Advanced Level</option>
                  </select>

                  <button 
                    type="submit"
                    disabled={studyLoading}
                    className="glow-btn bg-gradient-to-r from-primary-600 to-primary-700 hover:from-primary-500 hover:to-primary-600 text-white font-bold rounded-xl px-8 py-3 transition shadow-lg shadow-primary-500/25 flex items-center gap-2 whitespace-nowrap disabled:opacity-50"
                  >
                    {studyLoading ? (
                      <>
                        <RefreshCw className="w-5 h-5 animate-spin" />
                        Researching...
                      </>
                    ) : (
                      <>
                        <Sparkles className="w-5 h-5" />
                        Generate Lesson
                      </>
                    )}
                  </button>
                </div>
              </div>

              {/* Suggestions chips */}
              <div className="flex flex-wrap gap-2 items-center">
                <span className="text-xs text-slate-400">Quick suggestions:</span>
                {['Barkhausen criterion', "Ohm's Law", 'Covalent bonds', 'Photosynthesis', 'French Revolution'].map(s => (
                  <button 
                    key={s} 
                    type="button"
                    onClick={() => setStudyTopic(s)}
                    className="text-xs bg-dark-900 hover:bg-dark-800 border border-white/5 rounded-full px-3 py-1 text-slate-300 transition"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </form>

            {/* Results Renderer */}
            {studyLoading && (
              <div className="glass-panel rounded-2xl p-12 border border-white/5 text-center flex flex-col items-center gap-4">
                <div className="p-4 bg-primary-600/10 border border-primary-500/20 text-primary-400 rounded-full animate-spin">
                  <RefreshCw className="w-8 h-8" />
                </div>
                <div>
                  <h4 className="text-lg font-bold text-white">Fanning out to MCP servers...</h4>
                  <p className="text-slate-400 text-sm mt-1 max-w-sm mx-auto">Retrieving documents from PDFs, personal notes, textbooks, and trusted web APIs. Please wait.</p>
                </div>
              </div>
            )}

            {studyResult && !studyLoading && (
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                
                {/* Main Explanation Block */}
                <div className="glass-panel rounded-2xl border border-white/5 shadow-lg lg:col-span-2 overflow-hidden flex flex-col">
                  {/* Lesson Navigation Header */}
                  <div className="bg-dark-900 border-b border-white/5 p-4 flex gap-2">
                    {[
                      { id: 'simple', label: 'Simple Explanation' },
                      { id: 'steps', label: 'Step-by-Step Breakdown' },
                      { id: 'analogy', label: 'Analogy & Example' },
                    ].map(st => (
                      <button
                        key={st.id}
                        onClick={() => setStudySubTab(st.id)}
                        className={`text-xs px-4 py-2 rounded-lg font-semibold transition ${
                          studySubTab === st.id 
                            ? 'bg-primary-500/15 text-primary-400 border border-primary-500/20' 
                            : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'
                        }`}
                      >
                        {st.label}
                      </button>
                    ))}
                  </div>

                  {/* Tab Contents */}
                  <div className="p-6 flex-grow space-y-4 text-slate-300 text-sm leading-relaxed overflow-y-auto max-h-[500px]">
                    {studySubTab === 'simple' && (
                      <div className="space-y-4">
                        <h3 className="text-xl font-bold text-white capitalize">{studyResult.topic}</h3>
                        <p>{studyResult.lesson?.explanation?.simple}</p>
                        
                        <div className="mt-6 space-y-3">
                          <h4 className="font-bold text-slate-200">Key Points to Memorize:</h4>
                          <ul className="space-y-2">
                            {studyResult.lesson?.explanation?.key_points?.map((pt, idx) => (
                              <li key={idx} className="flex gap-3 items-start">
                                <span className="w-5 h-5 rounded-full bg-primary-500/10 border border-primary-500/20 text-primary-400 flex items-center justify-center text-xs flex-shrink-0 mt-0.5">{idx + 1}</span>
                                <span>{pt}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      </div>
                    )}

                    {studySubTab === 'steps' && (
                      <div className="space-y-4">
                        <h4 className="text-lg font-bold text-white">Chronological Step-by-Step Breakdown</h4>
                        <div className="space-y-4">
                          {studyResult.lesson?.explanation?.step_by_step?.map((step, idx) => (
                            <div key={idx} className="flex gap-4 items-start p-3 bg-dark-900/30 border border-white/5 rounded-xl">
                              <span className="text-2xl font-black text-primary-500/40 select-none">{(idx + 1).toString().padStart(2, '0')}</span>
                              <p className="m-0 text-slate-300">{step}</p>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {studySubTab === 'analogy' && (
                      <div className="space-y-6">
                        <div className="space-y-2 p-5 bg-accent-purple/5 border border-accent-purple/10 rounded-xl relative overflow-hidden">
                          <div className="absolute top-0 right-0 w-24 h-24 bg-accent-purple rounded-full filter blur-3xl opacity-10"></div>
                          <h4 className="font-bold text-accent-purple flex items-center gap-2">
                            <Sparkles className="w-5 h-5" />
                            Real-World Analogy
                          </h4>
                          <p className="italic text-slate-300 text-sm leading-relaxed">{studyResult.lesson?.analogy}</p>
                        </div>

                        {studyResult.lesson?.examples?.worked_example && (
                          <div className="space-y-3">
                            <h4 className="font-bold text-slate-200">Worked Example Walkthrough</h4>
                            <div className="bg-dark-900 p-5 border border-white/5 rounded-xl font-mono text-xs whitespace-pre-wrap leading-loose">
                              {studyResult.lesson.examples.worked_example}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>

                  {/* Summary Footer */}
                  <div className="bg-dark-900/60 p-4 border-t border-white/5 text-xs text-slate-400 italic">
                    <span className="font-bold text-slate-300 not-italic uppercase tracking-wide mr-2 text-[10px]">Summary:</span>
                    {studyResult.lesson?.summary}
                  </div>
                </div>

                {/* Sources & Flashcards Panel */}
                <div className="space-y-6">
                  
                  {/* Sources Panel */}
                  <div className="glass-panel rounded-2xl p-6 border border-white/5 shadow-lg space-y-4">
                    <div className="flex justify-between items-center">
                      <h3 className="font-bold text-white flex items-center gap-2">
                        <FileText className="w-5 h-5 text-accent-cyan" />
                        Research Sources
                      </h3>
                      
                      {/* Confidence score indicator */}
                      <div className="flex items-center gap-1.5">
                        <span className="text-[10px] uppercase font-bold text-slate-400">Confidence</span>
                        <span className="text-xs bg-green-500/10 border border-green-500/25 px-2 py-0.5 rounded-lg text-green-400 font-bold">
                          {Math.round(studyResult.research?.confidence_score * 100)}%
                        </span>
                      </div>
                    </div>

                    <div className="space-y-2 max-h-[150px] overflow-y-auto">
                      {studyResult.research?.sources && studyResult.research.sources.length > 0 ? (
                        studyResult.research.sources.map((src, idx) => (
                          <div key={idx} className="p-2 bg-dark-900 border border-white/5 rounded-lg text-xs flex items-center gap-2 text-slate-300 truncate">
                            <span className="w-4 h-4 bg-accent-cyan/10 text-accent-cyan rounded flex items-center justify-center font-bold text-[10px] flex-shrink-0">{idx + 1}</span>
                            <span className="truncate" title={src}>{src}</span>
                          </div>
                        ))
                      ) : (
                        <div className="p-3 text-center border border-dashed border-white/5 rounded-lg text-slate-500 text-xs">
                          No sources recorded. Generated using general LLM knowledge.
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Interactive Flashcards */}
                  {studyResult.lesson?.flashcards && studyResult.lesson.flashcards.length > 0 && (
                    <div className="glass-panel rounded-2xl p-6 border border-white/5 shadow-lg space-y-4">
                      <h3 className="font-bold text-white flex items-center gap-2">
                        <Award className="w-5 h-5 text-accent-purple" />
                        Flashcard Revision ({activeCardIndex + 1}/{studyResult.lesson.flashcards.length})
                      </h3>
                      
                      {/* Card Container */}
                      <div 
                        onClick={() => setCardFlipped(!cardFlipped)}
                        className="h-44 w-full bg-dark-900 hover:bg-dark-800 border border-white/10 hover:border-primary-500/30 rounded-xl p-6 flex flex-col justify-between items-center text-center cursor-pointer transition select-none relative"
                      >
                        <span className="text-[10px] uppercase font-bold text-slate-500 tracking-wider absolute top-4">
                          {cardFlipped ? 'Answer Definition' : 'Concept Term'}
                        </span>
                        
                        <div className="my-auto flex items-center justify-center">
                          <p className="text-sm font-semibold text-slate-100">
                            {cardFlipped 
                              ? studyResult.lesson.flashcards[activeCardIndex].back 
                              : studyResult.lesson.flashcards[activeCardIndex].front
                            }
                          </p>
                        </div>
                        
                        <span className="text-[10px] text-primary-400 font-semibold uppercase tracking-wider mb-2">
                          Click to Flip Card
                        </span>
                      </div>

                      {/* Pagination Controls */}
                      <div className="flex justify-between gap-4">
                        <button
                          disabled={activeCardIndex === 0}
                          onClick={() => {
                            setActiveCardIndex(prev => prev - 1);
                            setCardFlipped(false);
                          }}
                          className="flex-grow bg-dark-900 border border-white/5 rounded-lg py-2 text-xs font-semibold text-slate-300 hover:bg-dark-800 transition disabled:opacity-30"
                        >
                          Previous
                        </button>
                        <button
                          disabled={activeCardIndex === studyResult.lesson.flashcards.length - 1}
                          onClick={() => {
                            setActiveCardIndex(prev => prev + 1);
                            setCardFlipped(false);
                          }}
                          className="flex-grow bg-dark-900 border border-white/5 rounded-lg py-2 text-xs font-semibold text-slate-300 hover:bg-dark-800 transition disabled:opacity-30"
                        >
                          Next
                        </button>
                      </div>
                    </div>
                  )}

                </div>
              </div>
            )}
          </div>
        )}

        {/* Quiz Arena Tab */}
        {currentTab === 'quiz' && (
          <div className="space-y-6 animate-fadeIn">
            <div>
              <h2 className="text-3xl font-extrabold text-white tracking-tight">Quiz Arena</h2>
              <p className="text-slate-400 text-sm">Self-assessment quiz generator evaluated by the Planning & Evaluation Agent.</p>
            </div>

            {/* Quiz Setup Panel */}
            {!activeQuiz && (
              <div className="glass-panel rounded-2xl p-6 border border-white/5 shadow-lg space-y-6 max-w-xl mx-auto">
                <h3 className="text-lg font-bold text-white flex items-center gap-2">
                  <Flame className="w-5 h-5 text-orange-400" />
                  Initiate Assessment
                </h3>

                <div className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">Number of Questions</label>
                      <select 
                        value={quizSetup.count}
                        onChange={e => setQuizSetup(prev => ({ ...prev, count: parseInt(e.target.value) }))}
                        className="w-full bg-dark-900 border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-primary-500 transition"
                      >
                        <option value="3">3 Questions (Speedrun)</option>
                        <option value="5">5 Questions (Standard)</option>
                        <option value="10">10 Questions (Complete)</option>
                      </select>
                    </div>

                    <div>
                      <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">Topic Focus</label>
                      <select 
                        value={quizSetup.topic}
                        onChange={e => setQuizSetup(prev => ({ ...prev, topic: e.target.value }))}
                        className="w-full bg-dark-900 border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-primary-500 transition"
                      >
                        <option value="">All Topics (General)</option>
                        <option value="physics">Physics</option>
                        <option value="chemistry">Chemistry</option>
                        <option value="algebra">Algebra</option>
                        <option value="history">History</option>
                      </select>
                    </div>
                  </div>

                  {/* Adaptive toggle */}
                  <div className="p-4 bg-primary-500/5 border border-primary-500/10 rounded-xl flex items-center justify-between">
                    <div>
                      <span className="text-sm font-semibold text-slate-200 block">Enable Adaptive Placement</span>
                      <span className="text-xs text-slate-400">Evaluation Agent analyzes your weak history to over-sample items you struggle with.</span>
                    </div>
                    <button
                      onClick={() => setQuizSetup(prev => ({ ...prev, adaptive: !prev.adaptive }))}
                      className={`w-12 h-6 rounded-full p-1 transition duration-200 ${
                        quizSetup.adaptive ? 'bg-primary-500' : 'bg-dark-900 border border-white/10'
                      }`}
                    >
                      <div className={`w-4 h-4 bg-white rounded-full shadow transition transform ${
                        quizSetup.adaptive ? 'translate-x-6' : 'translate-x-0'
                      }`}></div>
                    </button>
                  </div>
                </div>

                <button 
                  onClick={handleStartQuiz}
                  disabled={quizLoading}
                  className="w-full glow-btn bg-gradient-to-r from-primary-600 to-primary-700 hover:from-primary-500 hover:to-primary-600 text-white font-bold rounded-xl py-3 shadow-lg shadow-primary-500/25 transition flex items-center justify-center gap-2 disabled:opacity-50"
                >
                  {quizLoading ? (
                    <>
                      <RefreshCw className="w-5 h-5 animate-spin" />
                      Constructing Assessment...
                    </>
                  ) : (
                    <>
                      <Flame className="w-5 h-5" />
                      Begin Quiz
                    </>
                  )}
                </button>
              </div>
            )}

            {/* Active Quiz View */}
            {activeQuiz && !quizSubmitted && (
              <div className="max-w-2xl mx-auto space-y-6">
                
                {/* Header status bar */}
                <div className="glass-panel rounded-2xl p-4 border border-white/5 flex justify-between items-center text-sm">
                  <div className="flex items-center gap-3">
                    <span className="px-2 py-1 bg-dark-900 border border-white/5 rounded-lg text-slate-300 font-bold font-mono">Quiz: {activeQuiz.quiz_id}</span>
                  </div>
                  
                  {/* Timer display */}
                  <div className="flex items-center gap-1.5 font-mono text-slate-300">
                    <Clock className="w-4 h-4 text-primary-400" />
                    <span>{Math.floor(quizTimer / 60)}:{(quizTimer % 60).toString().padStart(2, '0')}</span>
                  </div>
                </div>

                {/* Questions List */}
                <div className="space-y-6">
                  {activeQuiz.questions.map((q, idx) => (
                    <div key={q.id} className="glass-panel rounded-2xl p-6 border border-white/5 shadow-lg space-y-4">
                      <div className="flex items-start gap-3">
                        <span className="w-6 h-6 rounded-full bg-primary-500/10 border border-primary-500/20 text-primary-400 flex items-center justify-center font-bold text-xs flex-shrink-0 mt-0.5">
                          {idx + 1}
                        </span>
                        <div className="space-y-1">
                          <p className="font-semibold text-slate-100">{q.text}</p>
                          <span className="text-[10px] uppercase font-bold text-accent-cyan bg-accent-cyan/10 border border-accent-cyan/20 px-2 py-0.5 rounded-lg tracking-wider block w-max">
                            {q.topic}
                          </span>
                        </div>
                      </div>

                      {/* Options */}
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pl-9">
                        {q.options?.map((option, oIdx) => {
                          const isSelected = quizAnswers[q.id] === option;
                          return (
                            <button
                              key={oIdx}
                              onClick={() => handleSelectOption(q.id, option)}
                              className={`text-left p-3.5 rounded-xl text-sm transition border ${
                                isSelected 
                                  ? 'bg-primary-500/15 border-primary-500 text-slate-100 shadow-inner' 
                                  : 'bg-dark-900 border-white/5 text-slate-300 hover:bg-dark-800'
                              }`}
                            >
                              {option}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>

                <div className="flex gap-4">
                  <button 
                    onClick={() => setActiveQuiz(null)}
                    className="flex-grow bg-dark-900 border border-white/5 text-slate-300 font-bold rounded-xl py-3 hover:bg-dark-800 transition text-center"
                  >
                    Cancel Quiz
                  </button>
                  <button 
                    onClick={handleSubmitQuiz}
                    disabled={quizLoading}
                    className="flex-grow bg-gradient-to-r from-primary-600 to-primary-700 hover:from-primary-500 hover:to-primary-600 text-white font-bold rounded-xl py-3 shadow-lg shadow-primary-500/25 transition flex items-center justify-center gap-2 disabled:opacity-50"
                  >
                    {quizLoading ? (
                      <>
                        <RefreshCw className="w-5 h-5 animate-spin" />
                        Evaluating...
                      </>
                    ) : (
                      <>
                        <CheckCircle className="w-5 h-5" />
                        Submit Answers
                      </>
                    )}
                  </button>
                </div>
              </div>
            )}

            {/* Quiz Result View */}
            {quizSubmitted && quizResult && (
              <div className="max-w-3xl mx-auto space-y-6">
                
                {/* Result Card Banner */}
                <div className="glass-panel rounded-2xl p-8 border border-white/5 shadow-lg text-center relative overflow-hidden">
                  <div className="absolute top-0 right-0 w-44 h-44 bg-green-500 rounded-full filter blur-[100px] opacity-10 pointer-events-none"></div>
                  
                  <div className="w-16 h-16 bg-green-500/10 border border-green-500/20 text-green-400 rounded-full flex items-center justify-center mx-auto mb-4">
                    <Award className="w-8 h-8" />
                  </div>
                  
                  <h3 className="text-2xl font-extrabold text-white">Quiz Evaluated Successfully!</h3>
                  <p className="text-slate-400 text-sm mt-1">Graded by the Evaluation Agent.</p>
                  
                  <div className="mt-6 flex justify-center items-baseline gap-2">
                    <span className="text-5xl font-black text-green-400">{quizResult.score}%</span>
                    <span className="text-slate-400 text-sm">score</span>
                  </div>
                  
                  <p className="text-xs text-slate-400 mt-2">
                    Correct Answers: <span className="font-bold text-slate-200">{quizResult.correct_count}</span> out of {quizResult.total_questions} questions.
                  </p>
                </div>

                {/* Score breakdown & study plans tabs */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  
                  {/* Detailed quiz answers review */}
                  <div className="glass-panel rounded-2xl p-6 border border-white/5 shadow-lg space-y-4">
                    <h4 className="font-bold text-white flex items-center gap-2 border-b border-white/5 pb-3">
                      <CheckCircle className="w-5 h-5 text-green-400" />
                      Graded Questions Review
                    </h4>
                    
                    <div className="space-y-4 max-h-[350px] overflow-y-auto pr-1">
                      {quizResult.graded_results?.map((res, idx) => (
                        <div key={idx} className="p-3 bg-dark-900/50 border border-white/5 rounded-xl space-y-2">
                          <div className="flex justify-between items-start gap-2">
                            <span className="text-xs text-slate-400 font-semibold capitalize">Q{idx+1} ({res.topic})</span>
                            {res.correct ? (
                              <span className="text-green-400 flex items-center gap-1 text-xs font-bold">
                                <CheckCircle className="w-3.5 h-3.5" /> Correct
                              </span>
                            ) : (
                              <span className="text-red-400 flex items-center gap-1 text-xs font-bold">
                                <XCircle className="w-3.5 h-3.5" /> Incorrect
                              </span>
                            )}
                          </div>
                          <p className="text-xs font-semibold text-slate-200">{res.student_answer ? `Your answer: ${res.student_answer}` : 'Unanswered'}</p>
                          {!res.correct && <p className="text-xs text-slate-400">Correct: <span className="font-semibold text-green-400">{res.correct_answer}</span></p>}
                          {res.explanation && (
                            <p className="text-[10px] text-slate-500 mt-1 border-t border-white/5 pt-1 italic">{res.explanation}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Study Planning & Revision */}
                  <div className="glass-panel rounded-2xl p-6 border border-white/5 shadow-lg space-y-4">
                    <h4 className="font-bold text-white flex items-center gap-2 border-b border-white/5 pb-3">
                      <Calendar className="w-5 h-5 text-primary-400" />
                      Adaptive Study Plan
                    </h4>

                    {quizResult.study_plan ? (
                      <div className="space-y-4 text-xs">
                        <div className="space-y-2">
                          <span className="font-bold text-slate-200 block uppercase tracking-wider text-[10px]">Daily Target ({quizResult.study_plan.daily_plan?.minutes_allotted} min)</span>
                          <div className="p-3 bg-dark-900 border border-white/5 rounded-xl space-y-2">
                            <span className="font-bold text-slate-300">{quizResult.study_plan.daily_plan?.focus_topic ? `Focus: ${quizResult.study_plan.daily_plan.focus_topic.toUpperCase()}` : 'General study'}</span>
                            <ul className="list-disc pl-4 space-y-1 text-slate-400">
                              {quizResult.study_plan.daily_plan?.activities?.map((act, i) => (
                                <li key={i}>{act}</li>
                              ))}
                            </ul>
                          </div>
                        </div>

                        <div className="space-y-2">
                          <span className="font-bold text-slate-200 block uppercase tracking-wider text-[10px]">Spaced Revision Schedule</span>
                          <div className="p-3 bg-dark-900 border border-white/5 rounded-xl space-y-1">
                            {quizResult.study_plan.revision_schedule && Object.keys(quizResult.study_plan.revision_schedule).length > 0 ? (
                              Object.entries(quizResult.study_plan.revision_schedule).map(([days, date]) => (
                                <div key={days} className="flex justify-between border-b border-white/5 py-1.5 last:border-0">
                                  <span className="text-slate-400 capitalize">{days.replace('_', ' ')}:</span>
                                  <span className="font-bold text-primary-400">{new Date(date).toLocaleDateString()}</span>
                                </div>
                              ))
                            ) : (
                              <span className="text-slate-500 italic">No revisions scheduled. Excellent score!</span>
                            )}
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="text-center text-slate-500 py-10">
                        No study plans generated.
                      </div>
                    )}
                  </div>
                </div>

                {/* Recommendations */}
                {quizResult.recommendations && quizResult.recommendations.length > 0 && (
                  <div className="glass-panel rounded-2xl p-6 border border-white/5 shadow-lg space-y-3">
                    <h4 className="font-bold text-white flex items-center gap-2">
                      <Sparkles className="w-5 h-5 text-accent-cyan" />
                      Evaluation Recommendations
                    </h4>
                    <ul className="list-disc pl-5 space-y-1 text-xs text-slate-400">
                      {quizResult.recommendations.map((rec, i) => (
                        <li key={i}>{rec}</li>
                      ))}
                    </ul>
                  </div>
                )}

                <button 
                  onClick={() => {
                    setActiveQuiz(null);
                    setQuizSubmitted(false);
                    setQuizResult(null);
                  }}
                  className="w-full bg-primary-600 hover:bg-primary-500 text-white font-bold rounded-xl py-3 shadow transition text-center"
                >
                  Return to Quiz Menu
                </button>
              </div>
            )}
          </div>
        )}

        {/* Upload Manager Tab */}
        {currentTab === 'upload' && (
          <div className="space-y-6 animate-fadeIn">
            <div>
              <h2 className="text-3xl font-extrabold text-white tracking-tight">Resource Upload</h2>
              <p className="text-slate-400 text-sm">Upload textbook PDFs, reading lists, or study notes for the Research Agent to search.</p>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              
              {/* Upload Form Card */}
              <div className="glass-panel rounded-2xl p-6 border border-white/5 shadow-lg lg:col-span-2 space-y-6">
                <h3 className="text-lg font-bold text-slate-200 flex items-center gap-2">
                  <Upload className="w-5 h-5 text-accent-cyan" />
                  Upload study assets
                </h3>

                <form onSubmit={handleIngestDocument} className="space-y-4">
                  {/* File Selector */}
                  <div className="border-2 border-dashed border-white/10 hover:border-primary-500/30 rounded-2xl p-8 text-center bg-dark-900/40 relative transition duration-300">
                    <input 
                      type="file" 
                      required
                      accept=".txt,.md,.pdf"
                      onChange={e => setUploadFile(e.target.files[0])}
                      className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                    />
                    <Upload className="w-10 h-10 text-slate-400 mx-auto mb-4 animate-float" />
                    <p className="text-sm font-semibold text-slate-200">
                      {uploadFile ? uploadFile.name : 'Click to select or drag and drop a file'}
                    </p>
                    <p className="text-xs text-slate-500 mt-2">Supports PDF, TXT, or MD documents (Max 15MB)</p>
                  </div>

                  {/* Metadata fields */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">Subject / Topic Focus (Optional)</label>
                      <input 
                        type="text" 
                        value={uploadTopic}
                        onChange={e => setUploadTopic(e.target.value)}
                        placeholder="e.g. Physics, History" 
                        className="w-full bg-dark-900 border border-white/10 rounded-xl px-4 py-3 text-white placeholder-slate-500 focus:outline-none focus:border-primary-500 transition"
                      />
                    </div>
                  </div>

                  <button
                    type="submit"
                    disabled={uploadLoading || !uploadFile}
                    className="w-full glow-btn bg-gradient-to-r from-primary-600 to-primary-700 hover:from-primary-500 hover:to-primary-600 text-white font-bold rounded-xl py-3 shadow-lg shadow-primary-500/25 transition flex items-center justify-center gap-2 disabled:opacity-50"
                  >
                    {uploadLoading ? (
                      <>
                        <RefreshCw className="w-5 h-5 animate-spin" />
                        Analyzing & Indexing...
                      </>
                    ) : (
                      <>
                        <CheckCircle className="w-5 h-5" />
                        Ingest & Ingest Vector Index
                      </>
                    )}
                  </button>
                </form>

                {/* Status messages */}
                {uploadMessage && (
                  <div className={`p-4 rounded-xl text-sm border flex gap-3 ${
                    uploadMessage.type === 'success' 
                      ? 'bg-green-950/20 border-green-500/20 text-green-300' 
                      : 'bg-red-950/20 border-red-500/20 text-red-300'
                  }`}>
                    <Info className="w-5 h-5 flex-shrink-0 mt-0.5" />
                    <span>{uploadMessage.text}</span>
                  </div>
                )}
              </div>

              {/* Ingested Documents List */}
              <div className="glass-panel rounded-2xl p-6 border border-white/5 shadow-lg space-y-4">
                <h3 className="text-md font-bold text-white flex items-center gap-2">
                  <FileText className="w-5 h-5 text-primary-400" />
                  Ingested Knowledge Base
                </h3>
                <p className="text-xs text-slate-400">List of documents embedded in local vector collections.</p>

                <div className="space-y-2 max-h-[350px] overflow-y-auto">
                  {dashboardData?.analytics_report?.performance_analytics?.total_documents_uploaded > 0 ? (
                    dashboardData.analytics_report.performance_analytics.total_documents_uploaded > 0 && dashboardData.analytics_report.progress_summary?.student_id && (
                      <div className="space-y-2">
                        {/* We retrieve uploaded docs from storage inside report */}
                        {dashboardData.analytics_report.performance_analytics.total_documents_uploaded > 0 && (
                          <div className="p-3 bg-dark-900 border border-white/5 rounded-xl text-xs flex flex-col gap-1 text-slate-300">
                            <span className="font-semibold text-slate-200">Active Ingested Files:</span>
                            <span className="text-[10px] text-slate-400">Total documents uploaded successfully: {dashboardData.analytics_report.performance_analytics.total_documents_uploaded}</span>
                            <span className="text-[10px] text-slate-400">Total study sessions recorded: {dashboardData.analytics_report.performance_analytics.total_sessions}</span>
                          </div>
                        )}
                      </div>
                    )
                  ) : (
                    <div className="p-4 bg-dark-900/40 border border-dashed border-white/5 rounded-xl text-center text-slate-500 text-xs">
                      No documents uploaded yet. Select files on the left to populate the Research Agent.
                    </div>
                  )}
                </div>
              </div>

            </div>
          </div>
        )}
      </main>
    </div>
  );
}
