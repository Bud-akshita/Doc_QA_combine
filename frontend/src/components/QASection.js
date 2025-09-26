import React, { useState, useEffect } from "react";
import {
  MessageCircle,
  Send,
  Mic,
  MicOff,
  Square,
  BookOpen,
} from "lucide-react";
import { formatTime } from "../utils/formatUtils";
import SpeechRecognition, {
  useSpeechRecognition,
} from "react-speech-recognition";

const QASection = ({
  selectedDocuments,
  conversations,
  qaMessage,
  references,
  onAskQuestion,
  onShowReferences,
}) => {
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [recordingTime, setRecordingTime] = useState(0);
  const [timer, setTimer] = useState(null);

  const {
    transcript,
    listening,
    resetTranscript,
    browserSupportsSpeechRecognition,
  } = useSpeechRecognition();

  // 🔹 Handle references clickable in answers
  useEffect(() => {
    const handleRefClick = (e) => {
      if (e.target.classList.contains("ref-link")) {
        e.preventDefault();
        e.stopPropagation();

        const refId = e.target.dataset.ref;
        const conversationItem = e.target.closest(".conversation-item");

        if (conversationItem) {
          const conversationId = conversationItem.id.replace("conv-", "");

          // Show references panel
          setTimeout(() => {
            onShowReferences(parseInt(conversationId));
          }, 50);

          // Scroll to reference after panel opens
          setTimeout(() => {
            const refElement = document.getElementById(`ref-${refId}`);
            if (refElement) {
              refElement.scrollIntoView({ behavior: "smooth", block: "nearest" });
              refElement.style.backgroundColor = "#fef3c7";
              setTimeout(() => {
                refElement.style.backgroundColor = "";
              }, 2000);
            }
          }, 400);
        }
      }
    };

    document.addEventListener("click", handleRefClick, true);
    return () => {
      document.removeEventListener("click", handleRefClick, true);
    };
  }, [onShowReferences]);

  // 🔹 Handle voice recording start
  const startRecording = () => {
    resetTranscript();
    setRecordingTime(0);

    SpeechRecognition.startListening({ continuous: true, language: "hi-IN" });

    const t = setInterval(() => {
      setRecordingTime((prev) => prev + 1);
    }, 1000);
    setTimer(t);
  };

  // 🔹 Handle voice recording stop
  const stopRecording = async () => {
    SpeechRecognition.stopListening();
    if (timer) clearInterval(timer);

    if (transcript.trim()) {
      setQuestion(transcript);
    }
  };

  // 🔹 Ask text question
  const handleAskQuestion = async () => {
    if (!question.trim()) return;

    setAsking(true);
    const currentQuestion = question;
    setQuestion("");

    try {
      await onAskQuestion(currentQuestion);
    } catch (error) {
      console.error("Error asking question:", error);
    } finally {
      setAsking(false);
    }
  };

  // 🔹 Format answer text with clickable references
  const formatAnswerWithRefs = (answer, refMap = {}) => {
    if (!answer) return "";
    if (!refMap || Object.keys(refMap).length === 0) return answer;

    // Handle both simple numeric references (1) and complex REF format ([REF:pg1c0])
    return answer
      .replace(/\((\d+)\)/g, (match, refId) => {
        // Handle simple numeric references like (1), (2), etc.
        if (refMap[refId]) {
          return `<span class="ref-link" data-ref="${refId}" style="color:#3b82f6;cursor:pointer;text-decoration:underline;">${match}</span>`;
        }
        return match;
      })
      .replace(/\(\[([^\]]+)\]\)/g, (match, refContent) => {
        // Handle complex REF format like ([REF:pg1c0, REF:pg1c1])
        const refs = refContent.split(',').map(ref => ref.trim());
        const clickableRefs = refs.map(ref => {
          // Extract the key from REF:key format or use the ref as is
          const refKey = ref.startsWith('REF:') ? ref.substring(4) : ref;
          if (refMap[refKey] || refMap[ref]) {
            return `<span class="ref-link" data-ref="${refKey}" style="color:#3b82f6;cursor:pointer;text-decoration:underline;">${ref}</span>`;
          }
          return ref;
        });
        return `([${clickableRefs.join(', ')}])`;
      });
  };

  return (
    <div className="qa-section">
      <h2>
        <MessageCircle className="section-icon" />
        Ask Questions About Your Documents
      </h2>

      {!browserSupportsSpeechRecognition && (
        <p>Your browser does not support speech recognition.</p>
      )}

      {selectedDocuments.length > 0 && (
        <div className="selected-docs-info">
          <p>Selected documents: {selectedDocuments.join(", ")}</p>
        </div>
      )}

      {qaMessage.text && (
        <div className={`message ${qaMessage.type}`}>{qaMessage.text}</div>
      )}

      <div className="conversation-area">
        {conversations.map((conv) => (
          <div
            key={conv.id}
            id={`conv-${conv.id}`}
            className="conversation-item"
          >
            <div className="question-bubble">
              <strong>Q:</strong> {conv.question}
            </div>
            <div className="answer-bubble">
              <div className="answer-header">
                <strong>A:</strong>
                {conv.references &&
                  Object.keys(conv.references).length > 0 && (
                    <button
                      onClick={() => onShowReferences(conv.id)}
                      className="references-button"
                      title="Show References"
                    >
                      <BookOpen size={16} />
                      References ({Object.keys(conv.references).length})
                    </button>
                  )}
              </div>
              {conv.loading ? (
                <span className="thinking">
                  <div className="loading-spinner"></div>
                  Thinking...
                </span>
              ) : (
                <div
                  className="answer-content"
                  dangerouslySetInnerHTML={{
                    __html: formatAnswerWithRefs(conv.answer, conv.references),
                  }}
                />
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

      {listening && (
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

      <div className="question-input-container">
        <button
          onClick={listening ? stopRecording : startRecording}
          disabled={asking}
          className={`voice-button ${listening ? "recording" : ""}`}
          title={
            listening ? "Stop Recording" : "Record Voice Question (Hindi)"
          }
        >
          {listening ? (
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
          disabled={asking || listening}
          onKeyPress={(e) => {
            if (e.key === "Enter" && !asking && !listening) {
              handleAskQuestion();
            }
          }}
        />
        <button
          onClick={handleAskQuestion}
          disabled={
            asking ||
            !question.trim() ||
            selectedDocuments.length === 0 ||
            listening
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
  );
};

export default QASection;