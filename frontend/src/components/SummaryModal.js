import React from "react";
import { File, X, Loader2 } from "lucide-react";

// Utility function to detect links and wrap them in <a>
const renderSummaryWithLinks = (text) => {
  if (!text) return null;

  // Regex to match URLs
  const urlRegex = /(https?:\/\/[^\s]+)/g;

  return text.split(urlRegex).map((part, index) => {
    if (urlRegex.test(part)) {
      return (
        <a
          key={index}
          href={part}
          target="_blank"
          rel="noopener noreferrer"
          className="text-blue-600 underline hover:text-blue-800"
        >
          {part}
        </a>
      );
    }
    return part;
  });
};

const SummaryModal = ({
  show,
  onClose,
  currentSummary,
  summaryMessage,
  setSummaryMessage,
  onRegenerateSummary,
  summaries,
  setSummaries,
  loadingSummary,
}) => {
  if (!show) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-content summary-modal"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <h2>
            <File className="section-icon" />
            Document Summary: {currentSummary?.document || "Loading..."}
          </h2>
          <button onClick={onClose} className="modal-close-button">
            <X className="close-icon" />
          </button>
        </div>

        <div className="modal-body">
          <div className="summary-content">
            {loadingSummary ? (
              // Loading state
              <div className="summary-loading">
                <div className="loading-container">
                  <Loader2 className="spinner-icon animate-spin" />
                  <div className="loading-text">Generating summary...</div>
                </div>
              </div>
            ) : currentSummary ? (
              // Summary content
              <>
                <div className="summary-text">
                  {renderSummaryWithLinks(currentSummary.summary)}
                </div>

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
                      setSummaries((prev) => {
                        const updated = { ...prev };
                        delete updated[currentSummary.document];
                        return updated;
                      });
                      onClose();
                      onRegenerateSummary();
                    }}
                    className="regenerate-summary-button"
                  >
                    Regenerate Summary
                  </button>
                </div>
              </>
            ) : (
              // No summary state
              <div className="no-summary">
                <p>No summary available</p>
              </div>
            )}
          </div>
        </div>

        {summaryMessage.text && (
          <div className={`modal-message ${summaryMessage.type}`}>
            {summaryMessage.text}
          </div>
        )}
      </div>
    </div>
  );
};

export default SummaryModal;
