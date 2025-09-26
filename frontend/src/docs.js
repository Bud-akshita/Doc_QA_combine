import React, { useState, useEffect, useCallback, useRef } from "react";
import {
  Upload,
  File,
  X,
  RefreshCw,
  Send,
  MessageCircle,
  History,
  ChevronDown,
  ChevronUp,
  Mic,
  MicOff,
  Square,
} from "lucide-react";
import "./docs.css";

const useTimedMessage = (initialState = { text: "", type: "" }) => {
  const [message, setMessage] = useState(initialState);
  const timeoutRef = useRef(null);

  const setTimedMessage = useCallback((newMessage) => {
    // Clear any existing timeout
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }

    setMessage(newMessage);

    // Set timeout to clear message after 5 seconds (adjust as needed)
    if (newMessage.text) {
      timeoutRef.current = setTimeout(() => {
        setMessage({ text: "", type: "" });
      }, 5000);
    }
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  return [message, setTimedMessage];
};

const DocumentManager = ({ token, onLogout }) => {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [docType, setDocType] = useState("");
  const [dragOver, setDragOver] = useState(false);

  // Q&A related states
  const [selectedDocuments, setSelectedDocuments] = useState([]);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [conversations, setConversations] = useState([]);

  // Voice recording states
  const [isRecording, setIsRecording] = useState(false);
  const [mediaRecorder, setMediaRecorder] = useState(null);
  const [recordingTime, setRecordingTime] = useState(0);
  const recordingTimerRef = useRef(null);

  // Chat history related states
  const [chatHistory, setChatHistory] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [showHistoryModal, setShowHistoryModal] = useState(false);
  const [expandedHistoryItems, setExpandedHistoryItems] = useState(new Set());

  // Use timed messages instead of regular state
  const [message, setMessage] = useTimedMessage({ text: "", type: "" });
  const [qaMessage, setQaMessage] = useTimedMessage({ text: "", type: "" });

  // Summary related states
  const [summaries, setSummaries] = useState({}); // Store summaries by document name
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [showSummaryModal, setShowSummaryModal] = useState(false);
  const [currentSummary, setCurrentSummary] = useState(null);
  const [summaryMessage, setSummaryMessage] = useTimedMessage({
    text: "",
    type: "",
  });

  // API base URL - adjust this to match your FastAPI server
  const API_BASE_URL = "http://localhost:8000";

  const fileInputRef = useRef(null);

  // Voice recording functions
  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream, {
        mimeType: 'audio/webm;codecs=opus'
      });
      
      const chunks = [];
      
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunks.push(event.data);
        }
      };

      recorder.onstop = () => {
        const audioBlob = new Blob(chunks, { type: 'audio/webm;codecs=opus' });
        processVoiceQuestion(audioBlob);
        // Stop all tracks to release the microphone
        stream.getTracks().forEach(track => track.stop());
      };

      recorder.start();
      setMediaRecorder(recorder);
      setIsRecording(true);
      setRecordingTime(0);
      
      // Start timer
      recordingTimerRef.current = setInterval(() => {
        setRecordingTime(prev => prev + 1);
      }, 1000);

      setQaMessage({ text: "Recording... Speak your question in Hindi", type: "info" });
    } catch (error) {
      console.error('Error starting recording:', error);
      setQaMessage({ text: "Could not access microphone. Please check permissions.", type: "error" });
    }
  };

  const stopRecording = () => {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      mediaRecorder.stop();
      setIsRecording(false);
      
      if (recordingTimerRef.current) {
        clearInterval(recordingTimerRef.current);
      }
      
      setQaMessage({ text: "Processing your voice question...", type: "info" });
    }
  };

  const processVoiceQuestion = async (audioBlob) => {
    if (selectedDocuments.length === 0) {
      setQaMessage({
        text: "Please select at least one document",
        type: "error",
      });
      return;
    }

    // Create new conversation entry
    const newConversation = {
      id: Date.now(),
      question: "🎤 Voice Question (Processing...)",
      answer: "",
      loading: true,
    };

    setConversations((prev) => [...prev, newConversation]);
    setAsking(true);

    try {
      // Convert audio blob to base64 or send as FormData
      const formData = new FormData();
      formData.append("filename", selectedDocuments[0]);
      formData.append("audio", audioBlob, "question.webm");

      // First, convert speech to text (you'll need a speech-to-text service)
      // For now, we'll use the Web Speech API if available, or you can integrate with a service
      const questionText = await speechToText(audioBlob);
      
      if (!questionText) {
        throw new Error("Could not convert speech to text");
      }

      // Update conversation with the actual question
      setConversations((prev) =>
        prev.map((conv) =>
          conv.id === newConversation.id
            ? { ...conv, question: `🎤 ${questionText}` }
            : conv
        )
      );

      // Now send the text question to your Hindi endpoint
      const textFormData = new FormData();
      textFormData.append("filename", selectedDocuments[0]);
      textFormData.append("question", questionText);

      const response = await fetch(`${API_BASE_URL}/documents/ask-question-hi`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
        },
        body: textFormData,
      });

      if (response.ok) {
        const data = await response.json();
        // Update the conversation with the Hindi answer
        setConversations((prev) =>
          prev.map((conv) =>
            conv.id === newConversation.id
              ? { 
                  ...conv, 
                  answer: data.answer_hindi,
                  loading: false,
                  englishAnswer: data.answer_english, // Store English version too
                }
              : conv
          )
        );
        setQaMessage({
          text: "Voice question answered successfully!",
          type: "success",
        });

        // Optional: Speak the answer using text-to-speech
        if ('speechSynthesis' in window) {
          const utterance = new SpeechSynthesisUtterance(data.answer_hindi);
          utterance.lang = 'hi-IN';
          window.speechSynthesis.speak(utterance);
        }
      } else {
        const errorData = await response.json();
        setConversations((prev) =>
          prev.map((conv) =>
            conv.id === newConversation.id
              ? {
                  ...conv,
                  answer: `Error: ${errorData.detail || "Failed to get answer"}`,
                  loading: false,
                }
              : conv
          )
        );
        setQaMessage({
          text: errorData.detail || "Failed to get answer",
          type: "error",
        });
      }
    } catch (error) {
      setConversations((prev) =>
        prev.map((conv) =>
          conv.id === newConversation.id
            ? {
                ...conv,
                answer: "Error processing voice question. Please try again.",
                loading: false,
              }
            : conv
        )
      );
      setQaMessage({ 
        text: "Error processing voice question. Please try again.", 
        type: "error" 
      });
      console.error("Voice question error:", error);
    } finally {
      setAsking(false);
    }
  };

  // Simple speech-to-text using Web Speech API
  const speechToText = (audioBlob) => {
    return new Promise((resolve, reject) => {
      if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
        // Fallback: you could integrate with Google Speech-to-Text API or similar
        setQaMessage({ 
          text: "Speech recognition not supported. Please type your question.", 
          type: "error" 
        });
        reject(new Error("Speech recognition not supported"));
        return;
      }

      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      const recognition = new SpeechRecognition();
      
      recognition.lang = 'hi-IN'; // Hindi language
      recognition.continuous = false;
      recognition.interimResults = false;

      recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        console.log(transcript)
        resolve(transcript);
      };

      recognition.onerror = (event) => {
        console.error('Speech recognition error:', event.error);
        reject(new Error(`Speech recognition error: ${event.error}`));
      };

      recognition.onend = () => {
        // If no result was captured, reject
        setTimeout(() => reject(new Error("No speech detected")), 100);
      };

      // Note: We can't directly use the recorded blob with Web Speech API
      // Instead, we need to start a new recording session
      navigator.mediaDevices.getUserMedia({ audio: true })
        .then(stream => {
          recognition.start();
          // Stop the stream after a short delay to trigger recognition
          setTimeout(() => {
            stream.getTracks().forEach(track => track.stop());
          }, 100);
        })
        .catch(reject);
    });
  };

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const fetchDocuments = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/documents`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setDocuments(Array.isArray(data) ? data : []);
      } else {
        setDocuments([]);
      }
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    } catch (err) {
      console.error("Error fetching docs:", err);
      setDocuments([]);
    } finally {
      setLoading(false);
    }
  }, [API_BASE_URL, token]);

  // Fetch chat history for selected documents
  const fetchChatHistory = async () => {
    if (selectedDocuments.length === 0) {
      setMessage({
        text: "Please select at least one document to view history",
        type: "error",
      });
      return;
    }

    setLoadingHistory(true);
    try {
      // Since the endpoint only accepts one document at a time,
      // we'll fetch history for the first selected document
      const documentName = selectedDocuments[0];

      const response = await fetch(
        `${API_BASE_URL}/documents/history/${encodeURIComponent(documentName)}`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );

      if (response.ok) {
        const data = await response.json();
        setChatHistory(Array.isArray(data) ? data : []);
        setShowHistoryModal(true);
      } else if (response.status === 404) {
        // Handle the case where no history exists for this document
        setChatHistory([]);
        setShowHistoryModal(true);
      } else {
        const errorData = await response.json();
        setMessage({
          text: errorData.detail || "Failed to fetch chat history",
          type: "error",
        });
      }
    } catch (error) {
      setMessage({
        text: "Network error while fetching chat history",
        type: "error",
      });
      console.error("Error fetching chat history:", error);
    } finally {
      setLoadingHistory(false);
    }
  };

  useEffect(() => {
    if (token) {
      fetchDocuments();
    }
  }, [token, fetchDocuments]);

  // Cleanup recording timer on unmount
  useEffect(() => {
    return () => {
      if (recordingTimerRef.current) {
        clearInterval(recordingTimerRef.current);
      }
    };
  }, []);

  const handleUpload = async () => {
    if (!selectedFile || !docType) {
      setMessage({
        text: "Please select a file and document type",
        type: "error",
      });
      return;
    }

    setUploading(true);
    setMessage({ text: "", type: "" });

    try {
      const formData = new FormData();
      formData.append("file", selectedFile);
      formData.append("doc_type", docType);

      const response = await fetch(`${API_BASE_URL}/documents/upload`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
        },
        body: formData,
      });

      if (response.ok) {
        const newDocument = await response.json();
        setDocuments((prev) => [newDocument, ...prev]);
        setMessage({ text: "File uploaded successfully!", type: "success" });
        setSelectedFile(null);
        setDocType("");
        if (fileInputRef.current) {
          fileInputRef.current.value = "";
        }
      } else {
        const errorData = await response.json();
        setMessage({
          text: errorData.detail || "Upload failed",
          type: "error",
        });
      }
    } catch (error) {
      setMessage({ text: "Network error. Please try again.", type: "error" });
      console.log(error);
    } finally {
      setUploading(false);
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setDragOver(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setDragOver(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);

    const files = e.dataTransfer.files;
    if (files.length > 0) {
      const file = files[0];
      setSelectedFile(file);
      setDocType(""); // Let user choose manually
    }
  };

  const clearSelection = () => {
    setSelectedFile(null);
    setDocType("");
    document.getElementById("file-input").value = "";
  };

  // Handle document selection for Q&A
  const handleDocumentSelect = (docName, isChecked) => {
    if (isChecked) {
      setSelectedDocuments((prev) => [...prev, docName]);
    } else {
      setSelectedDocuments((prev) => prev.filter((name) => name !== docName));
    }
  };

  // Handle asking questions (text-based)
  const handleAskQuestion = async () => {
    if (!question.trim()) {
      setQaMessage({
        text: "Please enter a question",
        type: "error",
      });
      return;
    }

    if (selectedDocuments.length === 0) {
      setQaMessage({
        text: "Please select at least one document",
        type: "error",
      });
      return;
    }

    // Create new conversation entry
    const newConversation = {
      id: Date.now(),
      question: question,
      answer: "",
      loading: true,
    };

    setConversations((prev) => [...prev, newConversation]);
    setAsking(true);
    setQaMessage({ text: "", type: "" });
    const currentQuestion = question;
    setQuestion(""); // Clear input immediately

    try {
      const formData = new FormData();
      formData.append("filename", selectedDocuments[0]);
      formData.append("question", currentQuestion);

      const response = await fetch(`${API_BASE_URL}/documents/ask-question`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
        },
        body: formData,
      });

      if (response.ok) {
        const data = await response.json();
        // Update the conversation with the answer
        setConversations((prev) =>
          prev.map((conv) =>
            conv.id === newConversation.id
              ? { ...conv, answer: data.answer, loading: false }
              : conv
          )
        );
        setQaMessage({
          text: "Question answered successfully!",
          type: "success",
        });
      } else {
        const errorData = await response.json();
        // Update the conversation with error
        setConversations((prev) =>
          prev.map((conv) =>
            conv.id === newConversation.id
              ? {
                  ...conv,
                  answer: `Error: ${
                    errorData.detail || "Failed to get answer"
                  }`,
                  loading: false,
                }
              : conv
          )
        );
        setQaMessage({
          text: errorData.detail || "Failed to get answer",
          type: "error",
        });
      }
    } catch (error) {
      // Update the conversation with error
      setConversations((prev) =>
        prev.map((conv) =>
          conv.id === newConversation.id
            ? {
                ...conv,
                answer: "Network error. Please try again.",
                loading: false,
              }
            : conv
        )
      );
      setQaMessage({ text: "Network error. Please try again.", type: "error" });
      console.log(error);
    } finally {
      setAsking(false);
    }
  };

  // Toggle expanded state for history items
  const toggleHistoryItem = (id) => {
    const newExpanded = new Set(expandedHistoryItems);
    if (newExpanded.has(id)) {
      newExpanded.delete(id);
    } else {
      newExpanded.add(id);
    }
    setExpandedHistoryItems(newExpanded);
  };

  const formatFileSize = (bytes) => {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  };

  const formatDate = (dateString) => {
    return new Date(dateString).toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const truncateText = (text, maxLength = 100) => {
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + "...";
  };

  const generateSummary = async () => {
    if (selectedDocuments.length === 0) {
      setMessage({
        text: "Please select at least one document to generate summary",
        type: "error",
      });
      return;
    }

    const documentName = selectedDocuments[0];

    // Check if we already have a summary for this document
    if (summaries[documentName]) {
      setCurrentSummary({
        document: documentName,
        summary: summaries[documentName],
      });
      setShowSummaryModal(true);
      return;
    }

    setLoadingSummary(true);
    setSummaryMessage({ text: "", type: "" });

    try {
      // Find the document to get its type
      const selectedDoc = documents.find(
        (doc) => doc.doc_name === documentName
      );

      if (!selectedDoc) {
        setSummaryMessage({
          text: "Selected document not found",
          type: "error",
        });
        return;
      }

      // Use FormData with CORRECT parameter names
      const formData = new FormData();
      formData.append("filename", documentName);
      formData.append("document_type", selectedDoc.doc_type); // Changed from doc_type to document_type

      console.log("Sending summary request with:", {
        document_type: selectedDoc.doc_type,
        filename: documentName,
      });

      const response = await fetch(`${API_BASE_URL}/documents/summary`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          // Don't set Content-Type for FormData, browser sets it automatically
        },
        body: formData,
      });

      if (response.ok) {
        const data = await response.json();

        setSummaries((prev) => ({
          ...prev,
          [documentName]: data.summary,
        }));

        setCurrentSummary({
          document: documentName,
          summary: data.summary,
        });

        setShowSummaryModal(true);
        setSummaryMessage({
          text: "Summary generated successfully!",
          type: "success",
        });
      } else {
        const errorData = await response.json();
        setSummaryMessage({
          text: errorData.detail || "Failed to generate summary",
          type: "error",
        });

        // Log the error for debugging
        console.error("Summary generation error:", errorData);
      }
    } catch (error) {
      setSummaryMessage({
        text: "Network error while generating summary",
        type: "error",
      });
      console.error("Error generating summary:", error);
    } finally {
      setLoadingSummary(false);
    }
  };

  return (
    <div className="document-manager">
      <div className="document-sidebar">
        <div className="sidebar-header">
          <h3>Your Documents</h3>
          <div className="header-actions">
            <button
              onClick={generateSummary}
              disabled={loadingSummary || selectedDocuments.length === 0}
              className="summary-button"
              title={
                selectedDocuments.length === 0
                  ? "Select a document to generate summary"
                  : "Generate Summary"
              }
            >
              <File
                className={`summary-icon ${loadingSummary ? "spinning" : ""}`}
              />
              {selectedDocuments.length > 0 && (
                <span className="selected-badge">
                  {selectedDocuments.length}
                </span>
              )}
            </button>

            <button
              onClick={fetchChatHistory}
              disabled={loadingHistory || selectedDocuments.length === 0}
              className="history-button"
              title={
                selectedDocuments.length === 0
                  ? "Select documents to view history"
                  : "View Chat History"
              }
            >
              <History
                className={`history-icon ${loadingHistory ? "spinning" : ""}`}
              />
              {selectedDocuments.length > 0 && (
                <span className="selected-badge">
                  {selectedDocuments.length}
                </span>
              )}
            </button>

            <button
              onClick={fetchDocuments}
              disabled={loading}
              className="refresh-button"
            >
              <RefreshCw
                className={`refresh-icon ${loading ? "spinning" : ""}`}
              />
            </button>
          </div>
        </div>

        <div className="document-list">
          {loading ? (
            <div className="loading-state">
              <div className="loading-spinner"></div>
              <p>Loading documents...</p>
            </div>
          ) : documents.length === 0 ? (
            <div className="empty-state">
              <File className="empty-icon" />
              <p>No documents yet</p>
              <p className="empty-subtitle">
                Upload your first document to get started
              </p>
            </div>
          ) : (
            documents.map((doc) => (
              <div key={doc.id} className="document-item">
                <div className="document-checkbox">
                  <input
                    type="checkbox"
                    id={`doc-${doc.id}`}
                    checked={selectedDocuments.includes(doc.doc_name)}
                    onChange={(e) =>
                      handleDocumentSelect(doc.doc_name, e.target.checked)
                    }
                    className="checkbox-input"
                  />
                  <label htmlFor={`doc-${doc.id}`} className="checkbox-label">
                    <div className="document-info">
                      <h4 className="document-name" title={doc.doc_name}>
                        {doc.doc_name}
                      </h4>
                      <p className="document-meta">
                        {doc.doc_type} • {formatDate(doc.uploaded_at)}
                      </p>
                    </div>
                  </label>
                </div>
              </div>
            ))
          )}
        </div>

        <div className="sidebar-footer">
          <button onClick={onLogout} className="logout-button">
            Logout
          </button>
        </div>
      </div>

      <div className="document-main">
        <div className="upload-section">
          <h2>Upload Document</h2>

          {message.text && (
            <div className={`message ${message.type}`}>{message.text}</div>
          )}

          <div
            className={`upload-area ${dragOver ? "drag-over" : ""} ${
              selectedFile ? "has-file" : ""
            }`}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
          >
            {selectedFile ? (
              <div className="selected-file">
                <div className="file-preview">
                  <div className="file-details">
                    <h4>{selectedFile.name}</h4>
                    <p>{formatFileSize(selectedFile.size)}</p>
                    <p>Type: {docType}</p>
                  </div>
                  <button onClick={clearSelection} className="clear-button">
                    <X className="clear-icon" />
                  </button>
                </div>
              </div>
            ) : (
              <>
                <Upload className="upload-icon" />
                <h3>Drop your file here</h3>
                <p>or click to browse</p>
                <input
                  type="file"
                  id="file-input"
                  className="file-input"
                  accept="*/*"
                  ref={fileInputRef}
                  onChange={(e) => {
                    if (e.target.files.length > 0) {
                      setSelectedFile(e.target.files[0]);
                      setDocType("");
                    }
                  }}
                />
              </>
            )}
          </div>

          {selectedFile && (
            <div className="upload-controls">
              <div className="form-group">
                <label htmlFor="doc-type">Document Type:</label>
                <select
                  id="doc-type"
                  value={docType}
                  onChange={(e) => setDocType(e.target.value)}
                  className="doc-type-select"
                >
                  <option value="">Select document type</option>
                  <option value="loan">Loan Documents</option>
                  <option value="insurance">Insurance Documents</option>
                  <option value="tenders">Tenders</option>
                  <option value="credit_card_terms">Credit Card Terms</option>
                  <option value="other">Other</option>
                </select>
              </div>

              <button
                onClick={handleUpload}
                disabled={uploading || !docType}
                className="upload-button"
              >
                {uploading ? (
                  <>
                    <div className="loading-spinner"></div>
                    Uploading...
                  </>
                ) : (
                  <>
                    <Upload className="button-icon" />
                    Upload File
                  </>
                )}
              </button>
            </div>
          )}
        </div>

        {/* Q&A Section */}
        <div className="qa-section">
          <h2>
            <MessageCircle className="section-icon" />
            Ask Questions About Your Documents
          </h2>

          {selectedDocuments.length > 0 && (
            <div className="selected-docs-info">
              <p>Selected documents: {selectedDocuments.join(", ")}</p>
            </div>
          )}

          {qaMessage.text && (
            <div className={`message ${qaMessage.type}`}>{qaMessage.text}</div>
          )}

          {/* Conversation Display Area - Show First */}
          <div className="conversation-area">
            {conversations.map((conv) => (
              <div key={conv.id} className="conversation-item">
                <div className="question-bubble">
                  <strong>Q:</strong> {conv.question}
                </div>
                <div className="answer-bubble">
                  <strong>A:</strong>{" "}
                  {conv.loading ? (
                    <span className="thinking">
                      <div className="loading-spinner"></div>
                      Thinking...
                    </span>
                  ) : (
                    conv.answer
                  )}
                </div>
              </div>
            ))}
            {conversations.length === 0 && (
              <div className="empty-conversation">
                Start a conversation by asking a question about your selected
                documents or record a voice message.
              </div>
            )}
          </div>

          {/* Voice Recording Status */}
          {isRecording && (
            <div className="recording-status">
              <div className="recording-indicator">
                <div className="recording-dot"></div>
                Recording... {formatTime(recordingTime)}
              </div>
              <button
                onClick={stopRecording}
                className="stop-recording-button"
                title="Stop Recording"
              >
                <Square className="stop-icon" />
                Stop Recording
              </button>
            </div>
          )}

          {/* Question Input with Voice - Inline with Buttons */}
          <div className="question-input-container">
            <button
              onClick={isRecording ? stopRecording : startRecording}
              disabled={asking}
              className={`voice-button ${isRecording ? "recording" : ""}`}
              title={isRecording ? "Stop Recording" : "Record Voice Question (Hindi)"}
            >
              {isRecording ? (
                <MicOff className="mic-icon" />
              ) : (
                <Mic className="mic-icon" />
              )}
            </button>
            
            <input
              type="text"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Ask a question about the selected documents..."
              className="question-input-inline"
              disabled={asking || isRecording}
              onKeyPress={(e) => {
                if (e.key === "Enter" && !asking && !isRecording) {
                  handleAskQuestion();
                }
              }}
            />
            <button
              onClick={handleAskQuestion}
              disabled={
                asking || !question.trim() || selectedDocuments.length === 0 || isRecording
              }
              className="ask-button-inline"
            >
              {asking ? (
                <div className="loading-spinner"></div>
              ) : (
                <Send className="button-icon" />
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Chat History Modal */}
      {showHistoryModal && (
        <div
          className="modal-overlay"
          onClick={() => setShowHistoryModal(false)}
        >
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>
                <History className="section-icon" />
                Chat History for {selectedDocuments[0]}
              </h2>
              <button
                onClick={() => setShowHistoryModal(false)}
                className="modal-close-button"
              >
                <X className="close-icon" />
              </button>
            </div>

            <div className="modal-body">
              {chatHistory.length === 0 ? (
                <div className="empty-history">
                  <MessageCircle className="empty-icon" />
                  <p>No chat history found for {selectedDocuments[0]}</p>
                  <p className="empty-subtitle">
                    Start asking questions to build your chat history
                  </p>
                </div>
              ) : (
                <div className="history-list">
                  {chatHistory.map((item) => (
                    <div key={item.id} className="history-item">
                      <div className="history-header">
                        <div className="history-meta">
                          <span className="history-date">
                            {formatDate(item.created_at)}
                          </span>
                        </div>
                        <button
                          onClick={() => toggleHistoryItem(item.id)}
                          className="expand-button"
                        >
                          {expandedHistoryItems.has(item.id) ? (
                            <ChevronUp className="expand-icon" />
                          ) : (
                            <ChevronDown className="expand-icon" />
                          )}
                        </button>
                      </div>

                      <div className="history-preview">
                        <div className="history-question">
                          <strong>Q:</strong> {truncateText(item.question)}
                        </div>
                        {expandedHistoryItems.has(item.id) && (
                          <div className="history-answer">
                            <strong>A:</strong> {item.answer}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Summary Modal */}
      {showSummaryModal && currentSummary && (
        <div
          className="modal-overlay"
          onClick={() => setShowSummaryModal(false)}
        >
          <div
            className="modal-content summary-modal"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <h2>
                <File className="section-icon" />
                Document Summary: {currentSummary.document}
              </h2>
              <button
                onClick={() => setShowSummaryModal(false)}
                className="modal-close-button"
              >
                <X className="close-icon" />
              </button>
            </div>

            <div className="modal-body">
              <div className="summary-content">
                <div className="summary-text">{currentSummary.summary}</div>

                <div className="summary-actions">
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(currentSummary.summary);
                      setSummaryMessage({
                        text: "Summary copied to clipboard!",
                        type: "success",
                      });
                    }}
                    className="copy-summary-button"
                  >
                    Copy Summary
                  </button>

                  <button
                    onClick={() => {
                      // Clear cached summary to force regeneration
                      setSummaries((prev) => {
                        const updated = { ...prev };
                        delete updated[currentSummary.document];
                        return updated;
                      });
                      setShowSummaryModal(false);
                      generateSummary();
                    }}
                    className="regenerate-summary-button"
                  >
                    Regenerate Summary
                  </button>
                </div>
              </div>
            </div>

            {summaryMessage.text && (
              <div className={`modal-message ${summaryMessage.type}`}>
                {summaryMessage.text}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default DocumentManager;